"""Транспорт мессенджера MAX: long polling GET /updates, ответы POST /messages.

Схема API: github.com/max-messenger/api-schema. Токен передаётся в заголовке Authorization.
Вся логика диалога — в dialog.py; здесь только приём и отправка.
"""
import asyncio
import logging
import re

import httpx

from . import config, dialog, guests, notify, speech

log = logging.getLogger("max_bot")
_client: httpx.AsyncClient | None = None
_admin_chat: dict[str, int | None] = {"id": int(config.MAX_ADMIN_CHAT_ID) if config.MAX_ADMIN_CHAT_ID else None}
TEL_RE = re.compile(r"TEL[^:]*:([+\d\s\-()]+)")


def _attachments(out: notify.Out) -> list[dict]:
    rows = [[{"type": "callback", "text": text[:64], "payload": payload} for text, payload in row] for row in out.buttons]
    if out.request_contact:
        rows.insert(0, [{"type": "request_contact", "text": "Поделиться номером"}])
    if out.link:
        rows.insert(0, [{"type": "link", "text": out.link[0], "url": out.link[1]}])
    if not rows:
        return []
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


async def _post(params: dict, out: notify.Out) -> bool:
    if _client is None:
        return False
    body = {"text": out.text[:4000], "format": "markdown", "attachments": _attachments(out)}
    resp = await _client.post(f"{config.MAX_API}/messages", params=params, json=body)
    if resp.status_code != 200:
        log.warning("send failed %s %s", resp.status_code, resp.text[:300])
        return False
    return True


async def send_out(user_id: int | None, out: notify.Out) -> bool:
    if not user_id:
        return False
    return await _post({"user_id": user_id}, out)


async def send_admin(text: str) -> bool:
    chat_id = _admin_chat["id"]
    if not chat_id:
        return False
    return await _post({"chat_id": chat_id}, notify.Out(text=text))


def _contact_phone(body: dict) -> str | None:
    for att in body.get("attachments") or []:
        if att.get("type") != "contact":
            continue
        payload = att.get("payload") or {}
        match = TEL_RE.search(payload.get("vcf_info") or "")
        if match:
            return match.group(1)
        info = payload.get("max_info") or {}
        if info.get("phone"):
            return str(info["phone"])
    return None


def _audio_url(body: dict) -> str | None:
    """Ссылка на голосовое сообщение (вложение типа audio)."""
    for att in body.get("attachments") or []:
        if att.get("type") in ("audio", "voice"):
            url = (att.get("payload") or {}).get("url")
            if url:
                return url
    return None


async def _deliver(user_id: int, outs: list[notify.Out]) -> None:
    for out in outs:
        await send_out(user_id, out)


async def _on_message(msg: dict) -> None:
    sender = msg.get("sender") or {}
    user_id = sender.get("user_id")
    chat_id = (msg.get("recipient") or {}).get("chat_id")
    body = msg.get("body") or {}
    text = (body.get("text") or "").strip()
    if text.startswith("/admin_here") and config.ADMIN_PASSWORD and text.split()[-1] == config.ADMIN_PASSWORD:
        _admin_chat["id"] = chat_id
        await _post({"chat_id": chat_id}, notify.Out(text="Этот чат подключён для уведомлений администратора."))
        return
    guest = await guests.by_channel(user_id, sender.get("first_name") or sender.get("name"), chat_id)
    phone = _contact_phone(body)
    audio_url = _audio_url(body)
    if phone:
        await _deliver(user_id, await dialog.handle(guest, phone=phone))
    elif audio_url:
        audio = await speech.download(audio_url, {"Authorization": config.MAX_BOT_TOKEN})
        await _deliver(user_id, await dialog.handle_voice(guest, audio, "voice.ogg"))
    elif text:
        await _deliver(user_id, await dialog.handle(guest, text=text))
    elif body.get("attachments"):
        log.info("unsupported attachments: %s", [(a.get("type"), sorted((a.get("payload") or {}).keys())) for a in body["attachments"]])


async def _on_callback(cb: dict) -> None:
    await _client.post(f"{config.MAX_API}/answers", params={"callback_id": cb["callback_id"]}, json={"notification": "…"})
    user = cb.get("user") or {}
    guest = await guests.by_channel(user["user_id"], user.get("first_name") or user.get("name"))
    await _deliver(user["user_id"], await dialog.handle(guest, payload=cb.get("payload", "")))


async def _on_started(upd: dict) -> None:
    user = upd.get("user") or {}
    guest = await guests.by_channel(user["user_id"], user.get("first_name") or user.get("name"), upd.get("chat_id"))
    await _deliver(user["user_id"], await dialog.handle(guest, payload="menu"))


async def handle(upd: dict) -> None:
    kind = upd.get("update_type")
    try:
        if kind == "message_created":
            await _on_message(upd["message"])
        elif kind == "message_callback":
            await _on_callback(upd["callback"])
        elif kind == "bot_started":
            await _on_started(upd)
    except Exception:
        log.exception("update handling failed: %s", kind)


async def run() -> None:
    global _client
    if not config.MAX_BOT_TOKEN:
        log.info("MAX_BOT_TOKEN не задан — бот MAX не запущен, работает веб-эмулятор")
        return
    marker = None
    _client = httpx.AsyncClient(headers={"Authorization": config.MAX_BOT_TOKEN}, timeout=httpx.Timeout(40.0))
    notify.register_max(send_out, send_admin)
    me = await _client.get(f"{config.MAX_API}/me")
    log.info("MAX bot: %s", me.text[:200])
    while True:
        try:
            params = {"timeout": 30, "types": "message_created,message_callback,bot_started"}
            if marker:
                params["marker"] = marker
            resp = await _client.get(f"{config.MAX_API}/updates", params=params)
            if resp.status_code != 200:
                log.warning("updates %s %s", resp.status_code, resp.text[:200])
                await asyncio.sleep(3)
                continue
            data = resp.json()
            marker = data.get("marker", marker)
            for upd in data.get("updates", []):
                asyncio.create_task(handle(upd))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("poll error: %s", exc)
            await asyncio.sleep(3)
