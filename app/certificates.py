"""Учёт подарочных сертификатов: продажа (приход), погашение (расход), остаток, срок действия, история."""
from datetime import date, timedelta

from . import db, events

DEFAULT_VALID_DAYS = 180


async def issue(number: str, amount: int, kind: str = "nominal", program_name: str | None = None,
                buyer_name: str = "", buyer_phone: str = "", owner_name: str = "", valid_days: int = DEFAULT_VALID_DAYS,
                actor: str = "") -> dict:
    """Продажа сертификата: номер уникален, остаток = номиналу."""
    number = number.strip().upper()
    if not number or amount <= 0:
        raise ValueError("Укажите номер и номинал")
    if await db.query_one("SELECT 1 AS x FROM certificates WHERE number = %s", (number,)):
        raise ValueError("Сертификат с таким номером уже есть")
    async with db.tx() as conn:
        cert = await db.fetchone(
            conn,
            """INSERT INTO certificates (number, kind, program_name, amount, balance, buyer_name, buyer_phone, owner_name, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (number, kind, program_name, amount, amount, buyer_name, buyer_phone, owner_name, date.today() + timedelta(days=valid_days)),
        )
        await conn.execute(
            "INSERT INTO certificate_ops (certificate_id, kind, amount, actor, note) VALUES (%s, 'sale', %s, %s, 'продажа')",
            (cert["id"], amount, actor),
        )
    events.publish("certificates")
    return cert


async def find(number: str) -> dict | None:
    cert = await db.query_one("SELECT * FROM certificates WHERE number = %s", (number.strip().upper(),))
    if not cert:
        return None
    if cert["status"] == "active" and cert["expires_at"] < date.today():
        cert = await db.query_one("UPDATE certificates SET status = 'expired' WHERE id = %s RETURNING *", (cert["id"],))
    cert["ops"] = await db.query(
        "SELECT kind, amount, booking_id, actor, note, created_at FROM certificate_ops WHERE certificate_id = %s ORDER BY id",
        (cert["id"],),
    )
    return cert


async def redeem(number: str, amount: int, booking_id: int | None = None, actor: str = "", note: str = "") -> dict:
    """Погашение (полное или частичное). Сверка: активен, не просрочен, хватает остатка."""
    cert = await find(number)
    if not cert:
        raise ValueError("Сертификат не найден — проверьте номер")
    if cert["status"] != "active":
        raise ValueError({"used": "Сертификат уже использован", "expired": "Срок действия сертификата истёк",
                          "cancelled": "Сертификат аннулирован"}[cert["status"]])
    if amount <= 0 or amount > cert["balance"]:
        raise ValueError(f"Сумма должна быть от 1 до {cert['balance']} ₽ (остаток)")
    async with db.tx() as conn:
        updated = await db.fetchone(
            conn,
            """UPDATE certificates SET balance = balance - %s,
                   status = CASE WHEN balance - %s = 0 THEN 'used' ELSE status END
               WHERE id = %s AND balance >= %s RETURNING *""",
            (amount, amount, cert["id"], amount),
        )
        if not updated:
            raise ValueError("Остаток изменился — обновите карточку")
        await conn.execute(
            "INSERT INTO certificate_ops (certificate_id, kind, amount, booking_id, actor, note) VALUES (%s, 'redeem', %s, %s, %s, %s)",
            (cert["id"], -amount, booking_id, actor, note),
        )
        if booking_id:
            await conn.execute(
                "UPDATE bookings SET payment_status = 'certificate', payment_method = %s WHERE id = %s",
                (f"сертификат {cert['number']}", booking_id),
            )
    events.publish("certificates")
    return await find(number)


async def cancel(number: str, actor: str = "") -> dict:
    cert = await find(number)
    if not cert:
        raise ValueError("Сертификат не найден")
    await db.query("UPDATE certificates SET status = 'cancelled' WHERE id = %s RETURNING id", (cert["id"],))
    await db.query(
        "INSERT INTO certificate_ops (certificate_id, kind, amount, actor, note) VALUES (%s, 'cancel', 0, %s, 'аннулирован') RETURNING id",
        (cert["id"], actor),
    )
    events.publish("certificates")
    return await find(number)


async def listing(status: str | None = None) -> dict:
    rows = await db.query(
        "SELECT * FROM certificates" + (" WHERE status = %s" if status else "") + " ORDER BY sold_at DESC LIMIT 300",
        (status,) if status else None,
    )
    totals = await db.query_one(
        """SELECT COALESCE(sum(amount), 0) AS sold, COALESCE(sum(amount - balance), 0) AS redeemed,
                  COALESCE(sum(balance) FILTER (WHERE status = 'active'), 0) AS outstanding,
                  count(*) FILTER (WHERE status = 'active') AS active
           FROM certificates WHERE status <> 'cancelled'"""
    )
    return {"items": rows, "totals": totals}
