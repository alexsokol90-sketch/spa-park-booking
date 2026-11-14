"""Шина событий для мгновенного обновления сетки администратора (Server-Sent Events)."""
import asyncio

_subscribers: set[asyncio.Queue] = set()


def publish(kind: str) -> None:
    for queue in list(_subscribers):
        if queue.full():
            continue
        queue.put_nowait(kind)


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)
