"""Транспорт ВКонтакте: бот сообщества через Bots Long Poll API. Логика диалога — в dialog.py.

Канал гостя: guests.vk_user_id. Чат администратора: VK_ADMIN_PEER_ID или команда `/admin <пароль>`.
Ограничения VK: inline-клавиатура — до 6 рядов и 10 кнопок, подпись — до 40 символов;
поделиться контактом кнопкой нельзя, телефон гость пишет сообщением.
"""
import asyncio
import json
import logging
import random
import re

import httpx

from . import config, dialog, guests, notify, settings, speech

log = logging.getLogger("vk_bot")
API = "https://api.vk.com/method/{method}"
VERSION = "5.199"
ADMIN_KEY = "vk_admin_peer_id"
MAX_ROWS = 6
MAX_BUTTONS = 10
_client: httpx.AsyncClient | None = None
_admin: dict[str, int | None] = {"peer": None}


async def call(method: str, **params) -> dict | list | int | None:
    if _client is None:
        return None
    params.update(access_token=config.VK_GROUP_TOKEN, v=VERSION)
    resp = await _client.post(API.format(method=method), data=params)
    data = resp.json()
    if "error" in data:
        log.warning("%s failed: %s", method, str(data["error"])[:300])
        return None
    return data.get("response")


def _plain(text: str) -> str:
    return re.sub(r"\*([^*\n]+)\*", r"\1", text)


def _vk_row(row: list[tuple[str, str]]) -> list[dict]:
    return [{"action": {"type": "callback", "label": text[:40], "payload": json.dumps({"p": payload})}} for text, payload in row]


def fit_rows(button_rows: list[list[tuple[str, str]]], reserved_rows: int = 0) -> list[list[tuple[str, str]]]:
    """Ряды в пределах лимитов VK; последний ряд (обычно «Готово»/«Меню») сохраняется всегда."""
    rows_limit, buttons_limit = MAX_ROWS - reserved_rows, MAX_BUTTONS - reserved_rows
    total = sum(len(r) for r in button_rows)
    if len(button_rows) > rows_limit and total <= buttons_limit:
        flat = [b for row in button_rows[:-1] for b in row]
        button_rows = [flat[i : i + 2] for i in range(0, len(flat), 2)] + [button_rows[-1]]
    if len(button_rows) <= rows_limit and total <= buttons_limit:
        return button_rows
    last = button_rows[-1]
    kept, used = [], len(last)
    for row in button_rows[:-1]:
        if len(kept) + 2 > rows_limit or used + len(row) > buttons_limit:
            break
        kept.append(row)
        used += len(row)
    return [*kept, last]


def keyboard(out: notify.Out) -> str | None:
    """Кнопки ответа в формате VK с учётом лимитов inline-клавиатуры."""
    rows: list[list[dict]] = []
    if out.link:
        rows.append([{"action": {"type": "open_link", "link": out.link[1], "label": out.link[0][:40]}}])
    if out.buttons:
        rows += [_vk_row(r) for r in fit_rows(out.buttons, reserved_rows=len(rows))]
    if not rows:
        return None
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


async def send_out(peer_id: int, out: notify.Out) -> bool:
    text = _plain(out.text)
    if out.request_contact:
        text += "\n\nНапишите номер телефона сообщением, например: +7 900 000-00-00"
    params = {"peer_id": peer_id, "message": text[:4000], "random_id": random.randint(1, 2**31 - 1)}
    markup = keyboard(out)
    if markup:
        params["keyboard"] = markup
    return await call("messages.send", **params) is not None


async def send_admin(text: str) -> bool:
    peer = _admin["peer"]
    if not peer:
        return False
    return await send_out(peer, notify.Out(text=text))


async def _user_name(user_id: int) -> str | None:
    users = await call("users.get", user_ids=user_id)
    return users[0].get("first_name") if users else None


async def _deliver(peer_id: int, outs: list[notify.Out]) -> None:
    for out in outs:
        await send_out(peer_id, out)


async def _guest(user_id: int) -> dict:
    return await guests.by_external("vk", user_id, await _user_name(user_id))


async def _on_admin_command(peer_id: int, text: str) -> bool:
    parts = text.split()
    if not parts or parts[0] != "/admin" or not config.ADMIN_PASSWORD:
        return False
    if len(parts) == 2 and parts[1] == config.ADMIN_PASSWORD:
        _admin["peer"] = peer_id
        await settings.put(ADMIN_KEY, str(peer_id))
        await send_out(peer_id, notify.Out(text="Этот чат подключён для уведомлений администратора СПА-парка."))
    else:
        await send_out(peer_id, notify.Out(text="Неверный пароль."))
    return True


def _button_payload(raw: str | dict | None) -> str | None:
    if not raw:
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    if data.get("command") == "start":
        return "menu"
    return data.get("p")


def _voice(msg: dict) -> dict | None:
    """Голосовое сообщение VK; поле transcript — готовая расшифровка от самого VK, если она есть."""
    for att in msg.get("attachments") or []:
        if att.get("type") == "audio_message":
            return att.get("audio_message") or {}
    return None


async def _on_message(msg: dict) -> None:
    user_id, peer_id = msg["from_id"], msg["peer_id"]
    text = (msg.get("text") or "").strip()
    if text.startswith("/admin") and await _on_admin_command(peer_id, text):
        return
    guest = await _guest(user_id)
    payload = _button_payload(msg.get("payload"))
    voice = _voice(msg)
    if voice:
        audio = None if voice.get("transcript") else await speech.download(voice.get("link_ogg") or voice.get("link_mp3") or "")
        await _deliver(peer_id, await dialog.handle_voice(guest, audio, "voice.ogg", text=voice.get("transcript")))
        return
    if payload:
        await _deliver(peer_id, await dialog.handle(guest, payload=payload))
    elif text.lower() in ("начать", "start", "/start"):
        await _deliver(peer_id, await dialog.handle(guest, payload="menu"))
    elif text:
        await _deliver(peer_id, await dialog.handle(guest, text=text))


async def _on_event(obj: dict) -> None:
    await call(
        "messages.sendMessageEventAnswer", event_id=obj["event_id"], user_id=obj["user_id"], peer_id=obj["peer_id"]
    )
    guest = await _guest(obj["user_id"])
    payload = _button_payload(obj.get("payload")) or "menu"
    await _deliver(obj["peer_id"], await dialog.handle(guest, payload=payload))


async def handle(update: dict) -> None:
    kind, obj = update.get("type"), update.get("object") or {}
    try:
        if kind == "message_new":
            await _on_message(obj["message"])
        elif kind == "message_event":
            await _on_event(obj)
    except Exception:
        log.exception("update handling failed: %s", kind)


async def _long_poll_server() -> dict | None:
    return await call("groups.getLongPollServer", group_id=config.VK_GROUP_ID)


async def run() -> None:
    global _client
    if not (config.VK_GROUP_TOKEN and config.VK_GROUP_ID):
        log.info("VK_GROUP_TOKEN / VK_GROUP_ID не заданы — бот VK не запущен")
        return
    _client = httpx.AsyncClient(timeout=httpx.Timeout(40.0))
    saved = config.VK_ADMIN_PEER_ID or await settings.get(ADMIN_KEY)
    _admin["peer"] = int(saved) if saved else None
    notify.register("vk", send_out, send_admin)
    server = await _long_poll_server()
    while True:
        if not server:
            await asyncio.sleep(5)
            server = await _long_poll_server()
            continue
        try:
            resp = await _client.get(server["server"], params={"act": "a_check", "key": server["key"], "ts": server["ts"], "wait": 25})
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("poll error: %s", exc)
            await asyncio.sleep(3)
            continue
        if "failed" in data:
            if data["failed"] == 1:
                server["ts"] = data["ts"]
            else:
                server = await _long_poll_server()
            continue
        server["ts"] = data["ts"]
        for upd in data.get("updates", []):
            asyncio.create_task(handle(upd))
