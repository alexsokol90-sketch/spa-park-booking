"""Перевод диалога на администратора: карточка в интерфейсе + уведомление в MAX с повтором."""
from . import db, events, guests, notify

REASONS = {
    "asked_admin": "Гость просит администратора",
    "out_of_kb": "Вопрос вне базы знаний",
    "complaint": "Негатив / жалоба / возврат денег",
    "group": "Групповой запрос (корпоратив, девичник, компания)",
    "health": "Сомнения по состоянию здоровья",
    "not_understood": "Ассистент дважды не понял запрос",
    "no_slots": "Нет подходящих окон",
}
HIGH_PRIORITY = {"complaint"}


async def create(guest_id: int, reason: str, details: str = "") -> dict:
    priority = "high" if reason in HIGH_PRIORITY else "normal"
    existing = await db.query_one(
        "SELECT * FROM escalations WHERE guest_id = %s AND reason = %s AND status = 'new' ORDER BY id DESC LIMIT 1",
        (guest_id, reason),
    )
    if existing:
        row = await db.query_one(
            """UPDATE escalations SET details = details || E'\n' || %s,
                   priority = CASE WHEN %s = 'high' THEN 'high' ELSE priority END
               WHERE id = %s RETURNING *""",
            (details, priority, existing["id"]),
        )
    else:
        row = await db.query_one(
            "INSERT INTO escalations (guest_id, reason, priority, details) VALUES (%s,%s,%s,%s) RETURNING *",
            (guest_id, reason, priority, details),
        )
        await notify_admin(row)
    events.publish("escalations")
    return row


async def notify_admin(esc: dict) -> None:
    guest = await guests.get(esc["guest_id"])
    who = guest.get("name") or "Гость"
    phone = guest.get("phone") or "телефон не указан"
    mark = "🔴 СРОЧНО" if esc["priority"] == "high" else "Новый запрос"
    text = (
        f"{mark}: {REASONS.get(esc['reason'], esc['reason'])}\n"
        f"Гость: {who}, {phone}\n"
        f"{esc['details']}\n"
        f"Карточка с историей диалога — в интерфейсе администратора, запрос №{esc['id']}"
    )
    await notify.to_admin(text, kind="escalation")
    await db.query(
        "UPDATE escalations SET notified_count = notified_count + 1, last_notified = now() WHERE id = %s RETURNING id",
        (esc["id"],),
    )


async def accept(esc_id: int) -> None:
    await db.query(
        "UPDATE escalations SET status = 'accepted', accepted_at = now() WHERE id = %s AND status = 'new' RETURNING id",
        (esc_id,),
    )
    events.publish("escalations")


async def close(esc_id: int) -> None:
    await db.query("UPDATE escalations SET status = 'closed' WHERE id = %s RETURNING id", (esc_id,))
    events.publish("escalations")


async def open_list() -> list[dict]:
    rows = await db.query(
        """SELECT e.*, g.name AS guest_name, g.phone AS guest_phone FROM escalations e
           JOIN guests g ON g.id = e.guest_id WHERE e.status <> 'closed'
           ORDER BY (e.priority = 'high') DESC, e.created_at DESC"""
    )
    for row in rows:
        row["history"] = await guests.history(row["guest_id"], limit=40)
        row["reason_title"] = REASONS.get(row["reason"], row["reason"])
    return rows


async def self_service_stats(days: int = 7) -> dict:
    """Доля обращений, закрытых ассистентом без администратора (цель кейса — не менее 80%)."""
    row = await db.query_one(
        """WITH active AS (
               SELECT DISTINCT guest_id FROM messages
               WHERE role = 'guest' AND created_at > now() - make_interval(days => %s)),
           escalated AS (
               SELECT DISTINCT guest_id FROM escalations WHERE created_at > now() - make_interval(days => %s))
           SELECT (SELECT count(*) FROM active) AS guests,
                  (SELECT count(*) FROM active a JOIN escalated e USING (guest_id)) AS escalated,
                  (SELECT count(*) FROM messages WHERE role = 'guest' AND created_at > now() - make_interval(days => %s)) AS messages""",
        (days, days, days),
    )
    reasons = await db.query(
        """SELECT reason, count(*) AS n FROM escalations WHERE created_at > now() - make_interval(days => %s)
           GROUP BY reason ORDER BY n DESC""",
        (days,),
    )
    guests = row["guests"] or 0
    share = 1 - (row["escalated"] / guests) if guests else None
    return {
        "days": days,
        "guests": guests,
        "messages": row["messages"],
        "escalated": row["escalated"],
        "self_service": share,
        "reasons": [{"title": REASONS.get(r["reason"], r["reason"]), "n": r["n"]} for r in reasons],
    }
