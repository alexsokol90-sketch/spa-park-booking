"""Транспорт Telegram (Bot API, long polling getUpdates). Логика диалога — в dialog.py.

Канал гостя: guests.tg_chat_id. Чат администратора: TG_ADMIN_CHAT_ID или команда `/admin <пароль>`.
"""
import asyncio
import html
import logging
import re

import httpx

from . import config, dialog, guests, notify, settings

log = logging.getLogger("tg_bot")
API = "{base}/bot{token}/{method}"
ADMIN_KEY = "tg_admin_chat_id"
BOLD_RE = re.compile(r"\*([^*\n]+)\*")
_client: httpx.AsyncClient | None = None
_admin: dict[str, int | None] = {"chat": None}


def _html(text: str) -> str:
    """Разметка *жирный* → HTML Telegram с экранированием остального текста."""
    return BOLD_RE.sub(r"<b>\1</b>", html.escape(text, quote=False))


async def call(method: str, **payload) -> dict | None:
    if _client is None:
        return None
    resp = await _client.post(API.format(base=config.TG_API_BASE, token=config.TG_BOT_TOKEN, method=method), json=payload)
    data = resp.json()
    if not data.get("ok"):
        log.warning("%s failed: %s", method, str(data)[:300])
        return None
    return data.get("result")


def _inline_keyboard(out: notify.Out) -> dict | None:
    rows = [[{"text": text[:64], "callback_data": payload[:64]} for text, payload in row] for row in out.buttons]
    if out.link:
        rows.insert(0, [{"text": out.link[0], "url": out.link[1]}])
    return {"inline_keyboard": rows} if rows else None


async def send_out(chat_id: int, out: notify.Out) -> bool:
    if out.request_contact:
        # Запросить контакт можно только обычной клавиатурой, не inline.
        markup = {
            "keyboard": [[{"text": "📱 Поделиться номером", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
    else:
        markup = _inline_keyboard(out)
    payload = {"chat_id": chat_id, "text": _html(out.text)[:4096], "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup:
        payload["reply_markup"] = markup
    return await call("sendMessage", **payload) is not None


async def send_admin(text: str) -> bool:
    chat_id = _admin["chat"]
    if not chat_id:
        return False
    return await call("sendMessage", chat_id=chat_id, text=text[:4096]) is not None


async def _deliver(chat_id: int, outs: list[notify.Out]) -> None:
    for out in outs:
        await send_out(chat_id, out)


async def _on_admin_command(chat_id: int, text: str) -> bool:
    parts = text.split()
    if parts[0] != "/admin" or not config.ADMIN_PASSWORD:
        return False
    if len(parts) == 2 and parts[1] == config.ADMIN_PASSWORD:
        _admin["chat"] = chat_id
        await settings.put(ADMIN_KEY, str(chat_id))
        await call("sendMessage", chat_id=chat_id, text="Этот чат подключён для уведомлений администратора СПА-парка.")
    else:
        await call("sendMessage", chat_id=chat_id, text="Неверный пароль.")
    return True


async def _on_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    sender = msg.get("from") or {}
    text = (msg.get("text") or "").strip()
    if text.startswith("/admin") and await _on_admin_command(chat_id, text):
        return
    guest = await guests.by_external("tg", chat_id, sender.get("first_name"))
    contact = msg.get("contact")
    if contact and contact.get("user_id") == sender.get("id"):
        await call("sendMessage", chat_id=chat_id, text="Спасибо, номер получен.", reply_markup={"remove_keyboard": True})
        await _deliver(chat_id, await dialog.handle(guest, phone=contact.get("phone_number", "")))
        return
    if text.startswith("/start"):
        if guest.get("lang") == "ru" and (sender.get("language_code") or "").startswith("en"):
            await guests.set_lang(guest["id"], "en")
            guest["lang"] = "en"
        await _deliver(chat_id, await dialog.handle(guest, payload="menu"))
    elif text:
        await _deliver(chat_id, await dialog.handle(guest, text=text))


async def _on_callback(cb: dict) -> None:
    await call("answerCallbackQuery", callback_query_id=cb["id"])
    message = cb.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id") or cb["from"]["id"]
    guest = await guests.by_external("tg", chat_id, cb["from"].get("first_name"))
    await _deliver(chat_id, await dialog.handle(guest, payload=cb.get("data", "")))


async def handle(update: dict) -> None:
    try:
        if "message" in update:
            await _on_message(update["message"])
        elif "callback_query" in update:
            await _on_callback(update["callback_query"])
    except Exception:
        log.exception("update handling failed")


async def run() -> None:
    global _client
    if not config.TG_BOT_TOKEN:
        log.info("TG_BOT_TOKEN не задан — бот Telegram не запущен")
        return
    _client = httpx.AsyncClient(timeout=httpx.Timeout(40.0))
    saved = config.TG_ADMIN_CHAT_ID or await settings.get(ADMIN_KEY)
    _admin["chat"] = int(saved) if saved else None
    notify.register("tg", send_out, send_admin)
    me = await call("getMe")
    log.info("Telegram bot: @%s", (me or {}).get("username"))
    await call(
        "setMyCommands",
        commands=[{"command": "start", "description": "Главное меню"}, {"command": "menu", "description": "Меню"}],
    )
    offset = None
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
            if offset:
                params["offset"] = offset
            updates = await call("getUpdates", **params)
            if updates is None:
                await asyncio.sleep(3)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                asyncio.create_task(handle(upd))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("poll error: %s", exc)
            await asyncio.sleep(3)
