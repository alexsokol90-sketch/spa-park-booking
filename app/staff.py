"""График мастеров и чек-листы смены.

График — источник правды для записи: окно предлагается только если мастер стоит в смене.
Чек-листы: открытие и закрытие смены (раз в день) и подготовка пространства к каждой брони.
"""
import json
from datetime import date, datetime, timedelta

from . import booking, config, db, events

PATTERNS = {"2/2": (2, 2), "5/2": (5, 2), "3/1": (3, 1), "1/1": (1, 1)}


def minutes(hhmm: str) -> int:
    """«10:00» → 600, «24:00» → 1440."""
    hours, mins = hhmm.split(":")
    value = int(hours) * 60 + int(mins)
    if not 0 <= value <= 1440:
        raise ValueError("Время вне суток")
    return value


def hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


# ---------- график ----------

async def schedule(start: date, days: int) -> dict:
    end = start + timedelta(days=days)
    masters = await db.query("SELECT id, name, skills FROM masters WHERE active ORDER BY id")
    shifts = await db.query(
        "SELECT master_id, day, start_min, end_min, note FROM master_shifts WHERE day >= %s AND day < %s", (start, end)
    )
    load = await db.query(
        """SELECT master_id, (starts_at AT TIME ZONE 'Asia/Yekaterinburg')::date AS day, count(*) AS n
           FROM bookings WHERE status IN ('hold', 'confirmed', 'completed')
             AND starts_at >= %s AND starts_at < %s GROUP BY 1, 2""",
        (booking.day_bounds(start)[0] - timedelta(hours=10), booking.day_bounds(end)[0]),
    )
    return {
        "days": [(start + timedelta(days=i)).isoformat() for i in range(days)],
        "masters": masters,
        "shifts": [{**s, "day": s["day"].isoformat(), "start": hhmm(s["start_min"]), "end": hhmm(s["end_min"])} for s in shifts],
        "load": [{**r, "day": r["day"].isoformat()} for r in load],
    }


async def conflicts(master_id: int, day: date, start_min: int | None, end_min: int | None) -> list[dict]:
    """Брони мастера, которые не помещаются в новую смену (или в выходной)."""
    rows = await db.query(
        booking.BOOKING_SELECT
        + " WHERE b.master_id = %s AND b.status IN ('hold', 'confirmed') AND b.starts_at >= %s AND b.starts_at < %s",
        (master_id, *booking.day_bounds(day)),
    )
    if start_min is None:
        return rows
    midnight = datetime(day.year, day.month, day.day, tzinfo=config.TZ)
    shift_start, shift_end = midnight + timedelta(minutes=start_min), midnight + timedelta(minutes=end_min)
    return [r for r in rows if r["starts_at"] < shift_start or r["master_until"] > shift_end]


async def set_shift(master_id: int, day: date, start: str | None, end: str | None, note: str = "") -> list[dict]:
    """Ставит смену (или выходной, если start пустой). Возвращает брони, оказавшиеся вне смены."""
    if not start:
        await db.query("DELETE FROM master_shifts WHERE master_id = %s AND day = %s RETURNING master_id", (master_id, day))
        found = await conflicts(master_id, day, None, None)
    else:
        start_min, end_min = minutes(start), minutes(end or "24:00")
        if end_min <= start_min:
            raise ValueError("Конец смены должен быть позже начала")
        await db.query(
            """INSERT INTO master_shifts (master_id, day, start_min, end_min, note) VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (master_id, day) DO UPDATE SET start_min = EXCLUDED.start_min,
                   end_min = EXCLUDED.end_min, note = EXCLUDED.note RETURNING master_id""",
            (master_id, day, start_min, end_min, note),
        )
        found = await conflicts(master_id, day, start_min, end_min)
    events.publish("schedule")
    events.publish("grid")
    return found


async def apply_pattern(master_id: int, first_day: date, days: int, pattern: str, start: str, end: str) -> int:
    """Заполняет график по шаблону «работаю N / отдыхаю M» начиная с first_day."""
    work, rest = PATTERNS[pattern]
    changed = 0
    for i in range(days):
        day = first_day + timedelta(days=i)
        on_duty = i % (work + rest) < work
        await set_shift(master_id, day, start if on_duty else None, end)
        changed += 1
    return changed


async def on_duty(day: date) -> list[dict]:
    """Кто из мастеров работает в этот день — для ответов ассистента."""
    rows = await db.query(
        """SELECT m.id, m.name, m.skills, s.start_min, s.end_min FROM master_shifts s
           JOIN masters m ON m.id = s.master_id WHERE s.day = %s AND m.active ORDER BY s.start_min, m.name""",
        (day,),
    )
    return [{**r, "start": hhmm(r["start_min"]), "end": hhmm(r["end_min"])} for r in rows]


async def master_days(master_id: int, days: int = 7) -> list[dict]:
    today = booking.now().date()
    rows = await db.query(
        """SELECT day, start_min, end_min FROM master_shifts WHERE master_id = %s AND day >= %s AND day < %s ORDER BY day""",
        (master_id, today, today + timedelta(days=days)),
    )
    return [{"day": r["day"], "start": hhmm(r["start_min"]), "end": hhmm(r["end_min"])} for r in rows]


# ---------- чек-листы ----------

async def _ensure_runs(day: date) -> None:
    """Создаёт выполнения на день: открытие/закрытие смены и подготовку к каждой брони."""
    templates = {t["kind"]: t for t in await db.query("SELECT * FROM checklist_templates WHERE active")}
    for kind in ("opening", "closing"):
        tpl = templates.get(kind)
        if tpl:
            await db.query(
                """INSERT INTO checklist_runs (template_id, day, title, items) VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (tpl["id"], day, tpl["title"], json.dumps(tpl["items"], ensure_ascii=False)),
            )
    tpl = templates.get("space")
    if not tpl:
        return
    for bk in await booking.day_bookings(day):
        if bk["status"] != "confirmed":
            continue
        pre = ", ".join(p["name"] for p in bk["preorders"]) or "без предзаказа"
        title = f"{tpl['title']}: {bk['space_name']} к {bk['starts_at'].astimezone(config.TZ):%H:%M} — {bk['program_name']}"
        items = [i.replace("{preorders}", pre).replace("{master}", bk["master_name"]) for i in tpl["items"]]
        await db.query(
            """INSERT INTO checklist_runs (template_id, day, booking_id, title, items) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING RETURNING id""",
            (tpl["id"], day, bk["id"], title, json.dumps(items, ensure_ascii=False)),
        )


async def checklists(day: date) -> list[dict]:
    await _ensure_runs(day)
    return await db.query(
        """SELECT r.*, t.kind, b.starts_at FROM checklist_runs r JOIN checklist_templates t ON t.id = r.template_id
           LEFT JOIN bookings b ON b.id = r.booking_id
           WHERE r.day = %s AND (r.booking_id IS NULL OR b.status IN ('confirmed', 'completed'))
           ORDER BY CASE t.kind WHEN 'opening' THEN 0 WHEN 'space' THEN 1 ELSE 2 END, b.starts_at NULLS FIRST""",
        (day,),
    )


async def toggle(run_id: int, index: int, who: str) -> dict:
    """Отмечает пункт (или снимает отметку). Кто и когда отметил — сохраняется."""
    async with db.tx() as conn:
        run = await db.fetchone(conn, "SELECT * FROM checklist_runs WHERE id = %s FOR UPDATE", (run_id,))
        if not run or not 0 <= index < len(run["items"]):
            raise ValueError("Пункт не найден")
        done = dict(run["done"])
        key = str(index)
        if key in done:
            done.pop(key)
        else:
            done[key] = {"by": who[:40], "at": booking.now().isoformat()}
        complete = len(done) == len(run["items"])
        row = await db.fetchone(
            conn,
            """UPDATE checklist_runs SET done = %s, completed_at = CASE WHEN %s THEN now() ELSE NULL END
               WHERE id = %s RETURNING *""",
            (json.dumps(done, ensure_ascii=False), complete, run_id),
        )
    events.publish("checklists")
    return row
