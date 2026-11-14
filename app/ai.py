"""ИИ-слой. Claude через официальный SDK; без ключа — тестовый режим (для демо без интернета/ключа)."""
import logging
import anthropic
from . import config, domain

log = logging.getLogger("ai")
_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None


def enabled() -> bool:
    return _client is not None


async def answer(history: list[dict], system: str | None = None) -> str:
    """history: [{"role": "user"|"assistant", "content": str}, ...], последний — user."""
    if _client is None:
        last = history[-1]["content"] if history else ""
        return f"[тестовый режим, ключ ИИ не задан] Вы написали: «{last[:300]}»"
    try:
        msg = await _client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            system=system or domain.SYSTEM_PROMPT,
            messages=history[-20:],
        )
    except anthropic.RateLimitError:
        return "Сервис ИИ сейчас перегружен, попробуйте через минуту."
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s: %s", e.status_code, e.message)
        return "Не получилось получить ответ ИИ. Попробуйте ещё раз."
    except anthropic.APIConnectionError:
        return "Нет связи с сервисом ИИ. Попробуйте позже."
    if msg.stop_reason == "refusal":
        return "Не могу помочь с этим запросом."
    return "".join(b.text for b in msg.content if b.type == "text").strip() or "…"
