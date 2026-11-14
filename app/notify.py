"""Исходящие сообщения гостям и администратору.

Транспорты (Telegram, VK, MAX) регистрируются при старте. Гости веб-эмулятора (отрицательный user_id)
получают сообщения через очередь, которую опрашивает страница чата.
"""
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from . import db, events, guests

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

# Колонка guests с идентификатором гостя в канале → отправитель сообщений канала.
CHANNEL_COLUMNS = {"tg": "tg_chat_id", "vk": "vk_user_id", "max": "max_user_id"}
_senders: dict[str, Sender] = {}
_admin_senders: dict[str, AdminSender] = {}
web_inbox: dict[int, list[dict]] = defaultdict(list)
admin_feed: list[dict] = []


def register(channel: str, sender: Sender, admin_sender: AdminSender) -> None:
    _senders[channel] = sender
    _admin_senders[channel] = admin_sender


def register_max(sender: Sender, admin_sender: AdminSender) -> None:
    register("max", sender, admin_sender)


def active_channels() -> list[str]:
    return sorted(_senders)


async def deliver(guest: dict, out: Out) -> bool:
    """Доставка в тот канал, через который гость общается с ассистентом."""
    max_id = guest.get("max_user_id")
    if max_id and max_id < 0:
        web_inbox[guest["id"]].append(out.as_dict())
        return True
    for channel, column in CHANNEL_COLUMNS.items():
        ext_id = guest.get(column)
        if ext_id and channel in _senders:
            return await _senders[channel](ext_id, out)
    return False


async def to_guest(guest: dict, out: Out, kind: str, booking_id: int | None = None, campaign_id: int | None = None) -> bool:
    """Проактивное сообщение. Повторная отправка того же kind по брони блокируется базой."""
    row = await db.query_one(
        """INSERT INTO outbox (guest_id, kind, text, booking_id, campaign_id) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id""",
        (guest["id"], kind, out.text, booking_id, campaign_id),
    )
    if row is None:
        return False
    await guests.log(guest["id"], "bot", out.text)
    await deliver(guest, out)
    return True


async def to_admin(text: str, kind: str = "info") -> None:
    """Уведомление администратору: в ленту интерфейса и в чаты администратора в мессенджерах."""
    admin_feed.append({"kind": kind, "text": text})
    del admin_feed[:-100]
    events.publish("admin_feed")
    for sender in _admin_senders.values():
        try:
            await sender(text)
        except Exception:
            log.exception("admin notify failed")
    log.info("admin notify [%s]: %s", kind, text.replace("\n", " ")[:200])
