"""Интеграционные тесты движка брони. Нужна PostgreSQL с применённой схемой и демо-данными."""
import asyncio
from datetime import timedelta

import pytest

from app import booking, db


async def _with_pool(coro_fn):
    await db.open_pool()
    try:
        return await coro_fn()
    finally:
        await db.close_pool()


async def _two_guests() -> list[int]:
    rows = await db.query("SELECT id FROM guests ORDER BY id DESC LIMIT 2")
    return [r["id"] for r in rows]


async def _cleanup(ids: list[int]) -> None:
    await db.query("UPDATE bookings SET status = 'cancelled' WHERE id = ANY(%s) RETURNING id", (ids,))


def test_concurrent_holds_only_one_wins():
    async def scenario():
        g1, g2 = await _two_guests()
        prog = await db.query_one("SELECT id FROM programs WHERE code = 'rl-head'")
        day = booking.now().date() + timedelta(days=3)
        slot = (await booking.find_slots(prog["id"], day))[0]
        results = await asyncio.gather(
            booking.create_hold(g1, prog["id"], slot.start, slot.master_id, "bot"),
            booking.create_hold(g2, prog["id"], slot.start, slot.master_id, "admin"),
            return_exceptions=True,
        )
        won = [r for r in results if isinstance(r, dict)]
        lost = [r for r in results if isinstance(r, booking.SlotTaken)]
        await _cleanup([r["id"] for r in won])
        return len(won), len(lost)

    assert asyncio.run(_with_pool(scenario)) == (1, 1)


def test_hold_then_confirm_and_slot_disappears():
    async def scenario():
        g1, _ = await _two_guests()
        prog = await db.query_one("SELECT id FROM programs WHERE code = 'rl-feet'")
        day = booking.now().date() + timedelta(days=4)
        slot = (await booking.find_slots(prog["id"], day))[0]
        hold = await booking.create_hold(g1, prog["id"], slot.start, None, "bot")
        confirmed = await booking.confirm(hold["id"])
        free_after = [s.start for s in await booking.free_slots_public(prog["id"], day)]
        await _cleanup([hold["id"]])
        return confirmed["status"], slot.start in free_after

    assert asyncio.run(_with_pool(scenario)) == ("confirmed", False)


def test_one_active_hold_per_guest():
    async def scenario():
        g1, _ = await _two_guests()
        prog = await db.query_one("SELECT id FROM programs WHERE code = 'rl-back'")
        day = booking.now().date() + timedelta(days=5)
        slots = await booking.find_slots(prog["id"], day)
        first = await booking.create_hold(g1, prog["id"], slots[0].start, None, "bot")
        second = await booking.create_hold(g1, prog["id"], slots[-1].start, None, "bot")
        rows = await db.query("SELECT id FROM bookings WHERE guest_id = %s AND status = 'hold'", (g1,))
        await _cleanup([first["id"], second["id"]])
        return [r["id"] for r in rows] == [second["id"]]

    assert asyncio.run(_with_pool(scenario))


def test_confirm_expired_hold_fails():
    async def scenario():
        g1, _ = await _two_guests()
        prog = await db.query_one("SELECT id FROM programs WHERE code = 'rl-ice'")
        day = booking.now().date() + timedelta(days=6)
        slot = (await booking.find_slots(prog["id"], day))[0]
        hold = await booking.create_hold(g1, prog["id"], slot.start, None, "bot")
        await db.query(
            "UPDATE bookings SET hold_expires_at = now() - interval '1 second' WHERE id = %s RETURNING id",
            (hold["id"],),
        )
        with pytest.raises(booking.BookingError):
            await booking.confirm(hold["id"])
        await _cleanup([hold["id"]])
        return True

    assert asyncio.run(_with_pool(scenario))


def test_slots_respect_master_schedule():
    """Окна предлагаются только в смену мастера: смена 10:00–12:00 → начало не позже 11:30."""
    async def scenario():
        day = booking.now().date() + timedelta(days=8)
        saved = await db.query("SELECT * FROM master_shifts WHERE day = %s", (day,))
        prog = await db.query_one("SELECT id FROM programs WHERE code = 'rl-head'")
        try:
            await db.query("DELETE FROM master_shifts WHERE day = %s RETURNING master_id", (day,))
            await db.query(
                "INSERT INTO master_shifts (master_id, day, start_min, end_min) VALUES (1, %s, 600, 720) RETURNING master_id",
                (day,),
            )
            slots = await booking.free_slots_public(prog["id"], day)
            return [(s.start.hour, s.start.minute, s.master_id) for s in slots]
        finally:
            await db.query("DELETE FROM master_shifts WHERE day = %s RETURNING master_id", (day,))
            for s in saved:
                await db.query(
                    "INSERT INTO master_shifts (master_id, day, start_min, end_min, note) VALUES (%s,%s,%s,%s,%s) RETURNING master_id",
                    (s["master_id"], s["day"], s["start_min"], s["end_min"], s["note"]),
                )

    slots = asyncio.run(_with_pool(scenario))
    assert slots, "должны быть окна в смену"
    assert all(master == 1 for _, _, master in slots)
    assert all(h * 60 + m + 30 <= 720 for h, m, _ in slots)
