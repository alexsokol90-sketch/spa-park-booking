"""Провайдер GigaChat (Сбер): российская языковая модель для размещения решения в РФ.

Авторизация: ключ авторизации → OAuth-токен на 30 минут. TLS: корневой сертификат НУЦ Минцифры
(certs/russian_trusted_root_ca.pem) поверх системного хранилища — проверка сертификатов не отключается.
Вызов инструментов — через functions / function_call в формате GigaChat API.
"""
import json
import logging
import ssl
import time
import uuid

import httpx

from . import config

log = logging.getLogger("gigachat")
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
CA_FILE = config.ROOT / "certs" / "russian_trusted_root_ca.pem"
_token: dict[str, object] = {"value": None, "expires": 0.0}


def enabled() -> bool:
    return bool(config.GIGACHAT_AUTH_KEY)


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(CA_FILE))
    return ctx


_client = httpx.AsyncClient(verify=_ssl_context(), timeout=httpx.Timeout(60.0)) if enabled() else None


async def _access_token() -> str:
    if _token["value"] and time.time() < float(_token["expires"]) - 60:
        return str(_token["value"])
    resp = await _client.post(
        OAUTH_URL,
        headers={"Authorization": f"Basic {config.GIGACHAT_AUTH_KEY}", "RqUID": str(uuid.uuid4()), "Accept": "application/json"},
        data={"scope": config.GIGACHAT_SCOPE},
    )
    resp.raise_for_status()
    data = resp.json()
    _token["value"] = data["access_token"]
    _token["expires"] = data["expires_at"] / 1000
    return str(_token["value"])


async def chat(messages: list[dict], functions: list[dict] | None = None, max_tokens: int = 1024) -> dict:
    """Один запрос к модели. Возвращает message ответа (content и, возможно, function_call)."""
    body: dict = {"model": config.GIGACHAT_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
    if functions:
        body["functions"] = functions
        body["function_call"] = "auto"
    resp = await _client.post(CHAT_URL, headers={"Authorization": f"Bearer {await _access_token()}"}, json=body)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def functions_from_tools(tools: list[dict]) -> list[dict]:
    """Описание инструментов в формате Anthropic → формат functions GigaChat."""
    return [{"name": t["name"], "description": t["description"], "parameters": t["input_schema"]} for t in tools]


async def run_agent(system: str, history: list[dict], tools: list[dict], run_tool, max_steps: int = 5) -> str:
    """Цикл «модель → инструмент → модель». run_tool(name, args) выполняет действие и возвращает текст."""
    messages = [{"role": "system", "content": system}, *history]
    functions = functions_from_tools(tools)
    text = ""
    for _ in range(max_steps):
        msg = await chat(messages, functions)
        text = (msg.get("content") or "").strip()
        call = msg.get("function_call")
        if not call:
            break
        args = call.get("arguments") or {}
        if isinstance(args, str):
            args = json.loads(args or "{}")
        messages.append({"role": "assistant", "content": msg.get("content") or "", "function_call": call})
        result = await run_tool(call["name"], args)
        messages.append({"role": "function", "name": call["name"], "content": json.dumps({"result": result}, ensure_ascii=False)})
    return text


async def generate(prompt: str, max_tokens: int = 600) -> str | None:
    try:
        msg = await chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("GigaChat error: %s", exc)
        return None
    return (msg.get("content") or "").strip() or None
