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

DAILY_KINDS = ("opening", "daily", "custom", "closing")
BOOKING_KINDS = ("space", "cleanup")
ROLES = ("admin", "master", "cleaning")
KINDS = ("opening", "daily", "space", "cleanup", "closing")


def _fill(items: list[str], bk: dict) -> list[str]:
    pre = ", ".join(p["name"] for p in bk["preorders"]) or "без предзаказа"
    return [i.replace("{preorders}", pre).replace("{master}", bk["master_name"]).replace("{space}", bk["space_name"]) for i in items]


def _hm(moment: datetime) -> str:
    return f"{moment.astimezone(config.TZ):%H:%M}"


def _booking_title(tpl: dict, bk: dict) -> str:
    if tpl["kind"] == "cleanup":
        return f"{tpl['title']}: {bk['space_name']} {_hm(bk['ends_at'])}–{_hm(bk['busy_until'])} после «{bk['program_name']}»"
    return f"{tpl['title']}: {bk['space_name']} к {_hm(bk['starts_at'])} — {bk['program_name']}"


async def _insert_run(tpl: dict, day: date, title: str, items: list[str], booking_id: int | None = None) -> None:
    await db.query(
        """INSERT INTO checklist_runs (template_id, day, booking_id, title, items) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT DO NOTHING RETURNING id""",
        (tpl["id"], day, booking_id, title, json.dumps(items, ensure_ascii=False)),
    )


async def _ensure_runs(day: date) -> None:
    """Выполнения на день: ежедневные чек-листы и по каждой брони — подготовка до и уборка после."""
    templates = await db.query("SELECT * FROM checklist_templates WHERE active ORDER BY sort, id")
    for tpl in templates:
        if tpl["kind"] in DAILY_KINDS:
            await _insert_run(tpl, day, tpl["title"], tpl["items"])
    per_booking = [t for t in templates if t["kind"] in BOOKING_KINDS]
    if not per_booking:
        return
    for bk in await booking.day_bookings(day):
        if bk["status"] not in ("confirmed", "completed"):
            continue
        for tpl in per_booking:
            await _insert_run(tpl, day, _booking_title(tpl, bk), _fill(tpl["items"], bk), bk["id"])


def _run_order(run: dict) -> tuple:
    if run["kind"] == "opening":
        return (0, "")
    if run["kind"] == "closing":
        return (3, "")
    moment = run["ends_at"] if run["kind"] == "cleanup" else run["starts_at"]
    return (1, moment.isoformat()) if moment else (2, run["title"])


async def checklists(day: date, role: str | None = None) -> list[dict]:
    await _ensure_runs(day)
    rows = await db.query(
        """SELECT r.*, t.kind, t.role, b.starts_at, b.ends_at, b.busy_until FROM checklist_runs r
           JOIN checklist_templates t ON t.id = r.template_id
           LEFT JOIN bookings b ON b.id = r.booking_id
           WHERE r.day = %s AND (r.booking_id IS NULL OR b.status IN ('confirmed', 'completed'))
             AND (t.active OR r.done <> '{}'::jsonb)""",
        (day,),
    )
    if role:
        rows = [r for r in rows if r["role"] == role]
    return sorted(rows, key=_run_order)


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


# ---------- редактирование шаблонов ----------

def _clean_items(items: list[str]) -> list[str]:
    cleaned = [i.strip()[:200] for i in items if i and i.strip()]
    if not cleaned:
        raise ValueError("В чек-листе должен быть хотя бы один пункт")
    return cleaned[:40]


def _check(role: str, kind: str) -> None:
    if role not in ROLES or kind not in KINDS:
        raise ValueError("Неизвестная роль или тип чек-листа")


async def templates() -> list[dict]:
    return await db.query("SELECT * FROM checklist_templates ORDER BY active DESC, sort, id")


async def _refresh_pending(template_id: int) -> None:
    """Сегодняшние и будущие выполнения без отметок пересоздаются по новому шаблону; начатые — не трогаем."""
    await db.query(
        "DELETE FROM checklist_runs WHERE template_id = %s AND day >= %s AND done = '{}'::jsonb RETURNING id",
        (template_id, booking.now().date()),
    )
    events.publish("checklists")


async def create_template(title: str, role: str, kind: str, items: list[str]) -> dict:
    _check(role, kind)
    row = await db.query_one(
        """INSERT INTO checklist_templates (code, title, kind, role, items, sort)
           VALUES ('custom-' || substr(md5(random()::text), 1, 8), %s, %s, %s, %s,
                   (SELECT COALESCE(max(sort), 0) + 1 FROM checklist_templates)) RETURNING *""",
        (title.strip()[:120], kind, role, json.dumps(_clean_items(items), ensure_ascii=False)),
    )
    events.publish("checklists")
    return row


async def update_template(template_id: int, title: str, role: str, kind: str, items: list[str], active: bool) -> dict:
    _check(role, kind)
    row = await db.query_one(
        """UPDATE checklist_templates SET title = %s, role = %s, kind = %s, items = %s, active = %s
           WHERE id = %s RETURNING *""",
        (title.strip()[:120], role, kind, json.dumps(_clean_items(items), ensure_ascii=False), active, template_id),
    )
    if not row:
        raise ValueError("Шаблон не найден")
    await _refresh_pending(template_id)
    return row
