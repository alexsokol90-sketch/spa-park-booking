"""Фоновые задачи.

Каждые 5 секунд: истечение захватов, предупреждение администратору за 2 минуты, повтор уведомлений
по непринятым запросам. Раз в день: подтверждение визитов (10:00), список неответивших (15:00),
поздравления именинников (11:00).
"""
import asyncio
import logging
from datetime import datetime, timedelta

from . import booking, config, db, escalation, events, guests, marketing, notify
from .texts import fmt_time, t

log = logging.getLogger("scheduler")
TICK_SECONDS = 5


async def expire_and_warn() -> None:
    async with db.tx() as conn:
        expired = await booking.expire_holds(conn)
        warn = await db.fetch(
            conn,
            """UPDATE bookings SET hold_warned = true
               WHERE status = 'hold' AND NOT hold_warned
                 AND hold_expires_at <= now() + make_interval(mins => %s)
               RETURNING id""",
            (config.HOLD_WARN_MINUTES,),
        )
    for row in warn:
        bk = await booking.get_booking(row["id"])
        who = "бот" if bk["source"] == "bot" else "администратор"
        await notify.to_admin(
            f"Через {config.HOLD_WARN_MINUTES} мин истекает захват ({who}): {bk['space_name']}, "
            f"{fmt_time(bk['starts_at'])}, {bk['program_name']}, гость {bk['guest_name'] or bk['guest_phone'] or '—'}",
            kind="hold_warning",
        )
    if expired or warn:
        events.publish("grid")


async def renotify_escalations() -> None:
    rows = await db.query(
        """SELECT * FROM escalations WHERE status = 'new'
           AND last_notified < now() - make_interval(mins => %s)""",
        (config.ESCALATION_RENOTIFY_MIN,),
    )
    for esc in rows:
        await escalation.notify_admin(esc)


async def request_visit_confirmations() -> int:
    """10:00 — просьба подтвердить завтрашний визит."""
    tomorrow = datetime.now(config.TZ).date() + timedelta(days=1)
    start, end = booking.day_bounds(tomorrow)
    rows = await db.query(
        """SELECT id FROM bookings WHERE status = 'confirmed' AND visit_status = 'none'
           AND starts_at >= %s AND starts_at < %s""",
        (start, end),
    )
    sent = 0
    for row in rows:
        bk = await booking.get_booking(row["id"])
        guest = await guests.get(bk["guest_id"])
        lang = guest["lang"] or "ru"
        program = bk["program_name_en"] if lang == "en" else bk["program_name"]
        text = t("visit_ask", lang, name=guest["name"] or "", time=fmt_time(bk["starts_at"]), program=program, master=bk["master_name"])
        out = notify.Out(
            text=text.lstrip(", "),
            buttons=[
                [(t("btn_visit_yes", lang), f"visit:{bk['id']}")],
                [(t("btn_reschedule", lang), f"resched:{bk['id']}"), (t("btn_cancel", lang), f"cancel:{bk['id']}")],
                [(t("btn_preorder", lang), f"pre:{bk['id']}")],
            ],
        )
        if await notify.to_guest(guest, out, "visit_request", booking_id=bk["id"]):
            sent += 1
        await db.query("UPDATE bookings SET visit_status = 'asked' WHERE id = %s RETURNING id", (bk["id"],))
    events.publish("grid")
    return sent


async def no_answer_list(day=None) -> list[dict]:
    """Гости, не ответившие на просьбу подтвердить визит, — для точечного обзвона."""
    day = day or datetime.now(config.TZ).date() + timedelta(days=1)
    start, end = booking.day_bounds(day)
    return await db.query(
        booking.BOOKING_SELECT
        + " WHERE b.status = 'confirmed' AND b.visit_status = 'asked' AND b.starts_at >= %s AND b.starts_at < %s ORDER BY b.starts_at",
        (start, end),
    )


async def report_no_answer() -> int:
    rows = await no_answer_list()
    if rows:
        lines = [f"• {fmt_time(r['starts_at'])} {r['guest_name'] or '—'} {r['guest_phone'] or ''} — {r['program_name']}" for r in rows]
        await notify.to_admin("Не подтвердили завтрашний визит — нужно позвонить:\n" + "\n".join(lines), kind="no_answer")
    else:
        await notify.to_admin("Все гости на завтра подтвердили визит.", kind="no_answer")
    return len(rows)


async def birthday_greetings() -> int:
    seg = marketing.SEGMENTS["birthday_today"]
    result = await marketing.send("birthday_today", seg["template"], "Поздравления именинников (авто)")
    return result["sent"]


DAILY_JOBS = [
    ("visit_confirm", config.CONFIRM_REQUEST_TIME, request_visit_confirmations),
    ("birthdays", config.BIRTHDAY_TIME, birthday_greetings),
    ("no_answer", config.NO_ANSWER_REPORT_TIME, report_no_answer),
]


async def run_daily() -> None:
    now = datetime.now(config.TZ)
    for name, at, job in DAILY_JOBS:
        if now.time() < at:
            continue
        claimed = await db.query_one(
            "INSERT INTO job_runs (job, run_day) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING job", (name, now.date())
        )
        if claimed:
            log.info("daily job %s: %s", name, await job())


JOBS_BY_NAME = {name: job for name, _, job in DAILY_JOBS}


async def loop() -> None:
    while True:
        try:
            await expire_and_warn()
            await renotify_escalations()
            await run_daily()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
