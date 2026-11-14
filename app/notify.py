"""Исходящие сообщения гостям и администратору.

Транспорт MAX регистрируется ботом при старте. Гости веб-эмулятора (отрицательный user_id)
получают сообщения через очередь, которую опрашивает страница чата.
"""
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from . import config, db, events, guests

log = logging.getLogger("notify")


@dataclass
class Out:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)
    request_contact: bool = False
    link: tuple[str, str] | None = None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "buttons": [[{"text": t, "payload": p} for t, p in row] for row in self.buttons],
            "request_contact": self.request_contact,
            "link": {"text": self.link[0], "url": self.link[1]} if self.link else None,
        }


Sender = Callable[[int, Out], Awaitable[bool]]
AdminSender = Callable[[str], Awaitable[bool]]

_max_sender: Sender | None = None
_max_admin_sender: AdminSender | None = None
web_inbox: dict[int, list[dict]] = defaultdict(list)
admin_feed: list[dict] = []


def register_max(sender: Sender, admin_sender: AdminSender) -> None:
    global _max_sender, _max_admin_sender
    _max_sender = sender
    _max_admin_sender = admin_sender


async def to_guest(guest: dict, out: Out, kind: str, booking_id: int | None = None, campaign_id: int | None = None) -> bool:
    """Отправка проактивного сообщения. Повторная отправка того же kind по брони блокируется базой."""
    row = await db.query_one(
        """INSERT INTO outbox (guest_id, kind, text, booking_id, campaign_id) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id""",
        (guest["id"], kind, out.text, booking_id, campaign_id),
    )
    if row is None:
        return False
    await guests.log(guest["id"], "bot", out.text)
    user_id = guest.get("max_user_id")
    if user_id and user_id < 0:
        web_inbox[guest["id"]].append(out.as_dict())
        return True
    if user_id and _max_sender:
        return await _max_sender(user_id, out)
    return True


async def to_admin(text: str, kind: str = "info") -> None:
    """Уведомление администратору: в ленту интерфейса и в чат администратора в MAX."""
    admin_feed.append({"kind": kind, "text": text})
    del admin_feed[:-100]
    events.publish("admin_feed")
    if _max_admin_sender and config.MAX_ADMIN_CHAT_ID:
        await _max_admin_sender(text)
    log.info("admin notify [%s]: %s", kind, text.replace("\n", " ")[:200])
