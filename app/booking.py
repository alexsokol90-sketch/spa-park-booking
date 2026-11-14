"""Движок бронирования.

Три шага: показ окна (find_slots) → захват на 15 минут (create_hold) → бронь (confirm).
Гарантия «ноль накладок» обеспечивается базой: EXCLUDE-ограничения no_space_overlap
и no_master_overlap, плюс уникальный индекс one_hold_per_guest.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from psycopg import errors

from . import config, db, events

ACTIVE = ("hold", "confirmed")


class SlotTaken(Exception):
    """Окно уже занято другой записью или захватом."""


class BookingError(Exception):
    """Операция с бронью невозможна (истёк захват, неверный статус и т.п.)."""


@dataclass
class Slot:
    program_id: int
    start: datetime
    master_id: int
    master_name: str
    guests: int = 1

    def as_dict(self) -> dict:
        return {
            "program_id": self.program_id,
            "start": self.start.isoformat(),
            "master_id": self.master_id,
            "master_name": self.master_name,
            "guests": self.guests,
        }


def now() -> datetime:
    return datetime.now(config.TZ)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, config.OPEN_TIME, tzinfo=config.TZ)
    end = datetime(day.year, day.month, day.day, tzinfo=config.TZ) + timedelta(hours=config.CLOSE_HOUR)
    return start, end


def _overlaps(a_start: datetime, a_end: datetime, intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(a_start < b_end and b_start < a_end for b_start, b_end in intervals)


async def expire_holds(conn) -> list[dict]:
    """Снимает просроченные захваты. Вызывается в каждой транзакции брони и фоновой задачей."""
    return await db.fetch(
        conn,
        """UPDATE bookings SET status = 'expired'
           WHERE status = 'hold' AND hold_expires_at <= now()
           RETURNING id, guest_id, source""",
    )


async def get_program(conn, program_id: int) -> dict:
    prog = await db.fetchone(
        conn,
        """SELECT p.*, s.name AS space_name, s.name_en AS space_name_en, s.is_relax
           FROM programs p JOIN spaces s ON s.id = p.space_id WHERE p.id = %s""",
        (program_id,),
    )
    if not prog:
        raise BookingError("Программа не найдена")
    return prog


async def _busy(conn, day: date) -> tuple[dict[int, list], dict[int, list]]:
    start, end = day_bounds(day)
    rows = await db.fetch(
        conn,
        """SELECT space_id, master_id, starts_at, master_until, busy_until FROM bookings
           WHERE status IN ('hold', 'confirmed') AND (status <> 'hold' OR hold_expires_at > now())
             AND starts_at < %s AND busy_until > %s""",
        (end, start - timedelta(hours=4)),
    )
    spaces: dict[int, list] = {}
    masters: dict[int, list] = {}
    for r in rows:
        spaces.setdefault(r["space_id"], []).append((r["starts_at"], r["busy_until"]))
        masters.setdefault(r["master_id"], []).append((r["starts_at"], r["master_until"]))
    return spaces, masters


def _candidate_starts(day: date, duration: int) -> list[datetime]:
    open_at, close_at = day_bounds(day)
    earliest = max(open_at, now() + timedelta(minutes=30))
    step = timedelta(minutes=config.SLOT_STEP_MIN)
    t = open_at
    out = []
    while t + timedelta(minutes=duration) <= close_at:
        if t >= earliest:
            out.append(t)
        t += step
    return out


async def _shifts(conn, day: date) -> dict[int, tuple[datetime, datetime]]:
    """Смены мастеров на день: master_id → (начало, конец)."""
    rows = await db.fetch(conn, "SELECT master_id, start_min, end_min FROM master_shifts WHERE day = %s", (day,))
    midnight = datetime(day.year, day.month, day.day, tzinfo=config.TZ)
    return {
        r["master_id"]: (midnight + timedelta(minutes=r["start_min"]), midnight + timedelta(minutes=r["end_min"]))
        for r in rows
    }


def _on_shift(master_id: int, start: datetime, end: datetime, shifts: dict[int, tuple[datetime, datetime]]) -> bool:
    shift = shifts.get(master_id)
    return bool(shift) and shift[0] <= start and end <= shift[1]


def _pick_master(
    start: datetime, end: datetime, masters: list[dict], busy: dict[int, list], shifts: dict[int, tuple[datetime, datetime]]
) -> dict | None:
    """Свободный мастер в смене; при равенстве — менее загруженный."""
    free = [
        m for m in masters
        if _on_shift(m["id"], start, end, shifts) and not _overlaps(start, end, busy.get(m["id"], []))
    ]
    if not free:
        return None
    return min(free, key=lambda m: len(busy.get(m["id"], [])))


def _spread(items: list, limit: int) -> list:
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1)
    return [items[round(i * step)] for i in range(limit)]


def price_for(prog: dict, guests: int) -> int | None:
    return prog["price_couple"] if guests >= 2 else prog["price"]


def default_guests(prog: dict) -> int:
    return 1 if prog["price"] is not None else 2


async def free_slots(conn, program_id: int, day: date, guests: int = 1, master_id: int | None = None) -> list[Slot]:
    prog = await get_program(conn, program_id)
    space_busy, master_busy = await _busy(conn, day)
    shifts = await _shifts(conn, day)
    masters = await db.fetch(conn, "SELECT id, name FROM masters WHERE active ORDER BY id")
    if master_id:
        masters = [m for m in masters if m["id"] == master_id]
    dur = timedelta(minutes=prog["duration_min"])
    master_dur = timedelta(minutes=prog["master_min"])
    cleanup = timedelta(minutes=prog["cleanup_min"])
    result = []
    for start in _candidate_starts(day, prog["duration_min"]):
        if _overlaps(start, start + dur + cleanup, space_busy.get(prog["space_id"], [])):
            continue
        master = _pick_master(start, start + master_dur, masters, master_busy, shifts)
        if master:
            result.append(Slot(program_id, start, master["id"], master["name"], guests))
    return result


async def free_slots_public(program_id: int, day: date) -> list[Slot]:
    async with db.tx() as conn:
        return await free_slots(conn, program_id, day)


async def find_slots(
    program_id: int, day: date, around: datetime | None = None, limit: int = 5, guests: int = 1, master_id: int | None = None
) -> list[Slot]:
    """Реальные свободные окна. around — желаемое время: берутся ближайшие к нему; master_id — к конкретному мастеру."""
    async with db.tx() as conn:
        slots = await free_slots(conn, program_id, day, guests, master_id)
    if around:
        slots = sorted(slots, key=lambda s: abs((s.start - around).total_seconds()))[:limit]
        return sorted(slots, key=lambda s: s.start)
    return _spread(slots, limit)


async def nearest_days_with_slots(program_id: int, days: int = 7, master_id: int | None = None) -> list[date]:
    today = now().date()
    out = []
    async with db.tx() as conn:
        for i in range(days):
            day = today + timedelta(days=i)
            if await free_slots(conn, program_id, day, master_id=master_id):
                out.append(day)
    return out


async def create_hold(
    guest_id: int, program_id: int, start: datetime, master_id: int | None, source: str, guests: int | None = None
) -> dict:
    """Шаг 2: захват окна на 15 минут. Предыдущий захват гостя снимается."""
    try:
        async with db.tx() as conn:
            await expire_holds(conn)
            await conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE guest_id = %s AND status = 'hold'", (guest_id,)
            )
            prog = await get_program(conn, program_id)
            guests = guests or default_guests(prog)
            price = price_for(prog, guests)
            if price is None:
                raise BookingError("Программа недоступна для такого числа гостей")
            end = start + timedelta(minutes=prog["duration_min"])
            master_until = start + timedelta(minutes=prog["master_min"])
            busy_until = end + timedelta(minutes=prog["cleanup_min"])
            if master_id is None:
                master_id = await _free_master_id(conn, start, master_until)
            row = await db.fetchone(
                conn,
                """INSERT INTO bookings (guest_id, program_id, space_id, master_id, starts_at, ends_at, master_until,
                       busy_until, status, source, hold_expires_at, guests_count, price_total)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'hold',%s, now() + make_interval(mins => %s), %s, %s)
                   RETURNING id""",
                (guest_id, program_id, prog["space_id"], master_id, start, end, master_until, busy_until, source,
                 config.HOLD_MINUTES, guests, price),
            )
    except errors.ExclusionViolation as exc:
        raise SlotTaken from exc
    events.publish("grid")
    return await get_booking(row["id"])


async def _free_master_id(conn, start: datetime, end: datetime) -> int:
    """Первый свободный мастер, чья смена целиком покрывает работу по программе."""
    local = start.astimezone(config.TZ)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_min = int((local - midnight).total_seconds() // 60)
    end_min = int((end.astimezone(config.TZ) - midnight).total_seconds() // 60)
    row = await db.fetchone(
        conn,
        """SELECT m.id FROM masters m
           JOIN master_shifts s ON s.master_id = m.id AND s.day = %s AND s.start_min <= %s AND s.end_min >= %s
           WHERE m.active AND NOT EXISTS (
               SELECT 1 FROM bookings b WHERE b.master_id = m.id AND b.status IN ('hold', 'confirmed')
                 AND tstzrange(b.starts_at, b.master_until) && tstzrange(%s, %s))
           ORDER BY m.id LIMIT 1""",
        (local.date(), start_min, end_min, start, end),
    )
    if not row:
        raise SlotTaken
    return row["id"]


async def confirm(booking_id: int, replaces_id: int | None = None) -> dict:
    """Шаг 3: захват превращается в бронь. Без живого захвата бронь не создаётся."""
    async with db.tx() as conn:
        await expire_holds(conn)
        row = await db.fetchone(
            conn,
            """UPDATE bookings SET status = 'confirmed', confirmed_at = now(), hold_expires_at = NULL
               WHERE id = %s AND status = 'hold' RETURNING id, guest_id""",
            (booking_id,),
        )
        if not row:
            raise BookingError("Время захвата истекло, окно освобождено")
        if replaces_id:
            await conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = %s AND guest_id = %s AND status = 'confirmed'",
                (replaces_id, row["guest_id"]),
            )
    events.publish("grid")
    return await get_booking(booking_id)


async def cancel(booking_id: int, guest_id: int | None = None) -> bool:
    sql = "UPDATE bookings SET status = 'cancelled' WHERE id = %s AND status IN ('hold', 'confirmed')"
    params: tuple = (booking_id,)
    if guest_id is not None:
        sql += " AND guest_id = %s"
        params = (booking_id, guest_id)
    async with db.tx() as conn:
        cur = await conn.execute(sql + " RETURNING id", params)
        done = await cur.fetchone() is not None
    if done:
        events.publish("grid")
    return done


BOOKING_SELECT = """
    SELECT b.*, p.name AS program_name, p.name_en AS program_name_en, b.price_total AS price, p.duration_min,
           p.cleanup_min, p.master_min, p.prepay, s.name AS space_name, s.name_en AS space_name_en, m.name AS master_name,
           g.name AS guest_name, g.phone AS guest_phone, g.lang AS guest_lang,
           COALESCE((SELECT json_agg(json_build_object('id', i.id, 'name', i.name, 'name_en', i.name_en,
                                                       'qty', bp.qty, 'price', i.price) ORDER BY i.id)
                     FROM booking_preorders bp JOIN preorder_items i ON i.id = bp.item_id
                     WHERE bp.booking_id = b.id), '[]'::json) AS preorders
    FROM bookings b
    JOIN programs p ON p.id = b.program_id
    JOIN spaces s ON s.id = b.space_id
    JOIN masters m ON m.id = b.master_id
    JOIN guests g ON g.id = b.guest_id
"""


async def get_booking(booking_id: int) -> dict:
    row = await db.query_one(BOOKING_SELECT + " WHERE b.id = %s", (booking_id,))
    if not row:
        raise BookingError("Бронь не найдена")
    return row


async def guest_upcoming(guest_id: int) -> list[dict]:
    return await db.query(
        BOOKING_SELECT + " WHERE b.guest_id = %s AND b.status = 'confirmed' AND b.starts_at > now() ORDER BY b.starts_at",
        (guest_id,),
    )


async def day_bookings(day: date) -> list[dict]:
    start, end = day_bounds(day)
    return await db.query(
        BOOKING_SELECT
        + """ WHERE b.status IN ('hold', 'confirmed', 'completed') AND b.starts_at < %s AND b.busy_until > %s
              AND (b.status <> 'hold' OR b.hold_expires_at > now()) ORDER BY b.starts_at""",
        (end, start),
    )


async def alternatives(program_id: int, wanted: datetime, limit: int = 3, guests: int = 1) -> list[Slot]:
    """После отказа: та же программа в пределах ±2 часов или похожая программа в то же время."""
    day = wanted.astimezone(config.TZ).date()
    window = timedelta(hours=2)
    same = [
        s for s in await find_slots(program_id, day, around=wanted, limit=10, guests=guests)
        if abs(s.start - wanted) <= window
    ]
    options = same[:limit]
    if len(options) < limit:
        for prog_id in await similar_programs(program_id, guests):
            near = await find_slots(prog_id, day, around=wanted, limit=1, guests=guests)
            if near and abs(near[0].start - wanted) <= window:
                options.append(near[0])
            if len(options) >= limit:
                break
    return sorted(options, key=lambda s: abs(s.start - wanted))[:limit]


async def similar_programs(program_id: int, guests: int = 1) -> list[int]:
    price_col = "p.price_couple" if guests >= 2 else "p.price"
    async with db.tx() as conn:
        base = await get_program(conn, program_id)
        rows = await db.fetch(
            conn,
            f"""SELECT p.id, p.tags, p.duration_min FROM programs p JOIN spaces s ON s.id = p.space_id
               WHERE p.active AND p.id <> %s AND s.is_relax = %s AND {price_col} IS NOT NULL""",
            (program_id, base["is_relax"]),
        )
    tags = set(base["tags"].split(","))

    def score(r: dict) -> tuple:
        common = len(tags & set(r["tags"].split(",")))
        return (-common, abs(r["duration_min"] - base["duration_min"]))

    return [r["id"] for r in sorted(rows, key=score) if tags & set(r["tags"].split(","))]
