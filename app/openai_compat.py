"""Провайдер для OpenAI-совместимых API: AI-агенты Timeweb Cloud (YandexGPT и др.), Yandex Cloud и т. п.

Инструменты вызываются через строгий JSON в ответе модели, а не через нативный function calling:
так одинаково работает с любой моделью, в том числе с той, что выбрана в настройках агента Timeweb.
"""
import json
import logging
import re

import httpx

from . import config

log = logging.getLogger("openai_compat")
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

PROTOCOL = """
Отвечай СТРОГО одним JSON-объектом без пояснений вокруг:
{"reply": "текст гостю или пустая строка", "tool": null или имя инструмента, "args": {аргументы}}
Доступные инструменты:
{tools}
Если нужен инструмент — укажи его в "tool"; результат придёт следующим сообщением, после чего дай итоговый "reply" с "tool": null.
"""


def enabled() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_API_KEY)


_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0)) if enabled() else None


async def chat(messages: list[dict], max_tokens: int = 800) -> str:
    resp = await _client.post(
        f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={"model": config.LLM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3, "stream": False},
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()


def tools_text(tools: list[dict]) -> str:
    lines = []
    for tool in tools:
        props = ", ".join(f"{name}: {spec.get('type')}" for name, spec in tool["input_schema"].get("properties", {}).items())
        lines.append(f"- {tool['name']}({props}) — {tool['description']}")
    return "\n".join(lines)


def parse_action(raw: str) -> dict:
    """JSON-ответ модели → {"reply", "tool", "args"}. Не-JSON считается обычным ответом."""
    match = JSON_RE.search(raw)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return {"reply": str(data.get("reply") or ""), "tool": data.get("tool"), "args": data.get("args") or {}}
        except json.JSONDecodeError:
            pass
    return {"reply": raw, "tool": None, "args": {}}


async def run_agent(system: str, history: list[dict], tools: list[dict], run_tool, max_steps: int = 4) -> str:
    known = {t["name"] for t in tools}
    messages = [{"role": "system", "content": system + PROTOCOL.replace("{tools}", tools_text(tools))}, *history]
    reply = ""
    for _ in range(max_steps):
        raw = await chat(messages)
        action = parse_action(raw)
        reply = action["reply"]
        if action["tool"] not in known:
            break
        result = await run_tool(action["tool"], action["args"])
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"Результат инструмента {action['tool']}: {result}"})
    return reply


async def generate(prompt: str, max_tokens: int = 600) -> str | None:
    try:
        return await chat([{"role": "user", "content": prompt}], max_tokens) or None
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("LLM error: %s", exc)
        return None
