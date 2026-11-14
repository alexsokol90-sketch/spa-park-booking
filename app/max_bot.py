"""Бот в мессенджере MAX: long polling GET /updates, ответы POST /messages.
Схема: github.com/max-messenger/api-schema. Токен — в заголовке Authorization."""
import asyncio
import logging
import httpx
from . import ai, config, domain

log = logging.getLogger("max_bot")
HISTORY: dict[int, list[dict]] = {}


def _keyboard():
    rows = [[{"type": "callback", "text": t, "payload": p}] for t, p in domain.QUICK_ACTIONS]
    if config.PUBLIC_URL:
        rows.append([{"type": "link", "text": "Открыть веб-сервис", "url": config.PUBLIC_URL}])
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


async def send(cli: httpx.AsyncClient, *, user_id=None, chat_id=None, text: str, keyboard=True):
    params = {"user_id": user_id} if user_id else {"chat_id": chat_id}
    body = {"text": text[:4000], "format": "markdown"}
    if keyboard:
        body["attachments"] = _keyboard()
    r = await cli.post(f"{config.MAX_API}/messages", params=params, json=body)
    if r.status_code != 200:
        log.warning("send failed %s %s", r.status_code, r.text[:300])


async def _reply(cli, uid, chat_id, text):
    if text.strip().lower() in ("/start", "start", "начать"):
        HISTORY.pop(uid, None)
        await send(cli, user_id=uid, chat_id=chat_id, text=domain.WELCOME)
        return
    h = HISTORY.setdefault(uid, [])
    h.append({"role": "user", "content": text})
    out = await ai.answer(h)
    h.append({"role": "assistant", "content": out})
    del h[:-20]
    await send(cli, user_id=uid, chat_id=chat_id, text=out)


async def handle(cli: httpx.AsyncClient, upd: dict):
    t = upd.get("update_type")
    if t == "bot_started":
        await send(cli, user_id=upd.get("user", {}).get("user_id"), chat_id=upd.get("chat_id"), text=domain.WELCOME)
    elif t == "message_created":
        m = upd["message"]
        uid = m.get("sender", {}).get("user_id")
        chat_id = m.get("recipient", {}).get("chat_id")
        text = (m.get("body") or {}).get("text") or ""
        if text:
            await _reply(cli, uid, chat_id, text)
    elif t == "message_callback":
        cb = upd["callback"]
        await cli.post(f"{config.MAX_API}/answers", params={"callback_id": cb["callback_id"]}, json={"notification": "Секунду…"})
        uid = cb.get("user", {}).get("user_id")
        await _reply(cli, uid, None, cb.get("payload", ""))


async def run():
    if not config.MAX_BOT_TOKEN:
        log.info("MAX_BOT_TOKEN не задан — бот не запущен")
        return
    marker = None
    async with httpx.AsyncClient(headers={"Authorization": config.MAX_BOT_TOKEN}, timeout=httpx.Timeout(40.0)) as cli:
        me = await cli.get(f"{config.MAX_API}/me")
        log.info("MAX bot: %s", me.text[:200])
        while True:
            try:
                params = {"timeout": 30, "types": "message_created,message_callback,bot_started"}
                if marker:
                    params["marker"] = marker
                r = await cli.get(f"{config.MAX_API}/updates", params=params)
                if r.status_code != 200:
                    log.warning("updates %s %s", r.status_code, r.text[:200]); await asyncio.sleep(3); continue
                data = r.json()
                marker = data.get("marker", marker)
                for u in data.get("updates", []):
                    asyncio.create_task(handle(cli, u))
            except (httpx.HTTPError, ValueError) as e:
                log.warning("poll error: %s", e); await asyncio.sleep(3)
