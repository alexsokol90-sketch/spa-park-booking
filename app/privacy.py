"""Персональные данные (152-ФЗ): журнал доступа, карточка гостя, выгрузка и удаление по запросу."""
from . import db, events


async def audit(actor: str, action: str, guest_id: int | None = None, details: str = "") -> None:
    await db.query(
        "INSERT INTO pd_access_log (actor, action, guest_id, details) VALUES (%s, %s, %s, %s) RETURNING id",
        (actor, action, guest_id, details[:500]),
    )


async def guest_card(guest_id: int) -> dict | None:
    guest = await db.query_one(
        """SELECT id, name, surname, phone, gender, birth_date, loyalty_card, loyalty_points, card_level, reg_source, reg_channel,
                  referral_code, lang, unsubscribed, deleted_at, created_at
           FROM guests WHERE id = %s""",
        (guest_id,),
    )
    if not guest:
        return None
    guest["consents"] = await db.query(
        """SELECT c.kind, c.granted, c.text_version, c.channel, c.created_at, t.text
           FROM consents c LEFT JOIN consent_texts t ON t.version = c.text_version AND t.kind = c.kind
           WHERE c.guest_id = %s ORDER BY c.created_at DESC""",
        (guest_id,),
    )
    guest["bookings"] = await db.query(
        """SELECT b.id, b.starts_at, b.status, b.price_total, p.name AS program_name, m.name AS master_name
           FROM bookings b JOIN programs p ON p.id = b.program_id JOIN masters m ON m.id = b.master_id
           WHERE b.guest_id = %s ORDER BY b.starts_at DESC LIMIT 50""",
        (guest_id,),
    )
    guest["access_log"] = await db.query(
        "SELECT actor, action, details, created_at FROM pd_access_log WHERE guest_id = %s ORDER BY id DESC LIMIT 20",
        (guest_id,),
    )
    return guest


async def export(guest_id: int) -> dict | None:
    """Все данные гостя одним документом — ответ на запрос субъекта ПДн."""
    card = await guest_card(guest_id)
    if not card:
        return None
    card["messages"] = await db.query(
        "SELECT role, text, created_at FROM messages WHERE guest_id = %s ORDER BY id", (guest_id,)
    )
    card["preorders"] = await db.query(
        """SELECT b.id AS booking_id, i.name, bp.qty FROM booking_preorders bp
           JOIN bookings b ON b.id = bp.booking_id JOIN preorder_items i ON i.id = bp.item_id
           WHERE b.guest_id = %s""",
        (guest_id,),
    )
    return card


async def erase(guest_id: int) -> bool:
    """Удаление ПДн по запросу: переписка удаляется, профиль обезличивается, будущие записи отменяются.
    Обезличенная история визитов остаётся для учёта загрузки."""
    async with db.tx() as conn:
        cur = await conn.execute(
            """UPDATE guests SET name = NULL, phone = NULL, birth_date = NULL, max_user_id = NULL,
                   max_chat_id = NULL, tg_chat_id = NULL, vk_user_id = NULL, loyalty_card = NULL, unsubscribed = true, deleted_at = now()
               WHERE id = %s AND deleted_at IS NULL RETURNING id""",
            (guest_id,),
        )
        if await cur.fetchone() is None:
            return False
        await conn.execute("DELETE FROM messages WHERE guest_id = %s", (guest_id,))
        await conn.execute("DELETE FROM sessions WHERE guest_id = %s", (guest_id,))
        await conn.execute("UPDATE escalations SET details = '[удалено по запросу]', status = 'closed' WHERE guest_id = %s", (guest_id,))
        await conn.execute("UPDATE outbox SET text = '[удалено по запросу]' WHERE guest_id = %s", (guest_id,))
        await conn.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE guest_id = %s AND status IN ('hold', 'confirmed') AND starts_at > now()",
            (guest_id,),
        )
    events.publish("grid")
    return True


async def access_log(limit: int = 100) -> list[dict]:
    return await db.query(
        """SELECT l.*, g.name AS guest_name FROM pd_access_log l LEFT JOIN guests g ON g.id = l.guest_id
           ORDER BY l.id DESC LIMIT %s""",
        (limit,),
    )
