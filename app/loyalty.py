"""Система лояльности и аналитика клиентов.

Бонусы: начисление за визит (Золотая карта — 5%, Платиновая — 10%), списание до 50% чека, подарки со сроком,
реферальная программа. История визитов и выручка — из броней: администратор отмечает «пришёл» и сумму оплаты
(касса не нужна; при подключении кассы/PMS сумма приходит оттуда).
Фильтры клиентов общие для рассылок и автоматизаций; поля и операторы — из белого списка.
"""
import secrets
import string
from datetime import date, datetime, timedelta

from . import config, db, events

CASHBACK = {"gold": 0.05, "platinum": 0.10}
MAX_REDEEM_SHARE = 0.5
REFERRAL_BONUS = 300
AGE_GROUPS = [(18, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79)]
REVENUE = "COALESCE(b.paid_amount, b.price_total)"


# ---------- бонусы ----------

async def add_bonus(guest_id: int, delta: int, kind: str, note: str = "", booking_id: int | None = None,
                    expires_at: datetime | None = None) -> int:
    """Движение бонусов; баланс гостя пересчитывается в той же транзакции. Возвращает новый баланс."""
    async with db.tx() as conn:
        await conn.execute(
            """INSERT INTO bonus_tx (guest_id, delta, kind, booking_id, expires_at, note)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (guest_id, delta, kind, booking_id, expires_at, note[:200]),
        )
        row = await db.fetchone(
            conn,
            """UPDATE guests SET loyalty_points = GREATEST(0, (SELECT COALESCE(sum(delta), 0) FROM bonus_tx WHERE guest_id = %s))
               WHERE id = %s RETURNING loyalty_points""",
            (guest_id, guest_id),
        )
    events.publish("clients")
    return row["loyalty_points"]


async def mark_visit(booking_id: int, attended: bool, paid: int | None = None, bonus_spent: int = 0) -> dict:
    """Отметка визита администратором: пришёл (сумма оплаты, списанные бонусы) или не пришёл."""
    bk = await db.query_one("SELECT b.*, g.card_level FROM bookings b JOIN guests g ON g.id = b.guest_id WHERE b.id = %s", (booking_id,))
    if not bk:
        raise ValueError("Бронь не найдена")
    if not attended:
        await db.query("UPDATE bookings SET status = 'no_show' WHERE id = %s RETURNING id", (booking_id,))
        events.publish("grid")
        return {"status": "no_show"}
    paid = bk["price_total"] if paid is None else paid
    balance = (await db.query_one("SELECT loyalty_points FROM guests WHERE id = %s", (bk["guest_id"],)))["loyalty_points"]
    # Бонусами — не больше половины стоимости программы и не больше баланса.
    bonus_spent = max(0, min(bonus_spent, balance, int(bk["price_total"] * MAX_REDEEM_SHARE)))
    await db.query(
        "UPDATE bookings SET status = 'completed', paid_amount = %s, bonus_spent = %s WHERE id = %s RETURNING id",
        (paid, bonus_spent, booking_id),
    )
    if bonus_spent:
        await add_bonus(bk["guest_id"], -bonus_spent, "redeem", "оплата бонусами", booking_id)
    accrued = await accrue_for_visit(booking_id, bk["guest_id"], paid, bk["card_level"])
    events.publish("grid")
    return {"status": "completed", "paid": paid, "bonus_spent": bonus_spent, "accrued": accrued}


async def accrue_for_visit(booking_id: int, guest_id: int, paid: int, level: str) -> int:
    done = await db.query_one("SELECT 1 AS x FROM bonus_tx WHERE booking_id = %s AND kind = 'accrual'", (booking_id,))
    if done or paid <= 0:
        return 0
    amount = int(paid * CASHBACK.get(level, CASHBACK["gold"]))
    await add_bonus(guest_id, amount, "accrual", f"кешбэк за визит №{booking_id}", booking_id)
    await _referral_reward(guest_id)
    return amount


async def _referral_reward(guest_id: int) -> None:
    """Пригласившему — бонусы после первого визита приглашённого."""
    guest = await db.query_one("SELECT referred_by FROM guests WHERE id = %s", (guest_id,))
    if not guest or not guest["referred_by"]:
        return
    visits = await db.query_one("SELECT count(*) AS n FROM bookings WHERE guest_id = %s AND status = 'completed'", (guest_id,))
    if visits["n"] == 1:
        await add_bonus(guest["referred_by"], REFERRAL_BONUS, "referral", f"друг #{guest_id} пришёл впервые")


async def expire_gifts() -> int:
    """Сгорание подарочных бонусов с истёкшим сроком (в пределах текущего баланса)."""
    rows = await db.query(
        """SELECT t.id, t.guest_id, t.delta FROM bonus_tx t
           WHERE t.kind IN ('gift', 'referral') AND t.expires_at < now()
             AND NOT EXISTS (SELECT 1 FROM bonus_tx e WHERE e.kind = 'expire' AND e.note = 'сгорание #' || t.id)"""
    )
    burned = 0
    for row in rows:
        balance = (await db.query_one("SELECT loyalty_points FROM guests WHERE id = %s", (row["guest_id"],)))["loyalty_points"]
        amount = min(balance, row["delta"])
        await add_bonus(row["guest_id"], -amount, "expire", f"сгорание #{row['id']}")
        burned += amount
    return burned


async def gift(guest_id: int, amount: int, days: int, note: str) -> int:
    expires = datetime.now(config.TZ) + timedelta(days=days)
    return await add_bonus(guest_id, amount, "gift", note, expires_at=expires)


# ---------- рефералы ----------

def new_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "SP" + "".join(secrets.choice(alphabet) for _ in range(5))


async def ensure_referral_code(guest_id: int) -> str:
    row = await db.query_one("SELECT referral_code FROM guests WHERE id = %s", (guest_id,))
    if row and row["referral_code"]:
        return row["referral_code"]
    code = new_referral_code()
    await db.query("UPDATE guests SET referral_code = %s WHERE id = %s RETURNING id", (code, guest_id))
    return code


async def apply_referral(guest_id: int, code: str) -> bool:
    """Новый гость пришёл по ссылке друга (start=ref_КОД)."""
    referrer = await db.query_one("SELECT id FROM guests WHERE referral_code = %s AND id <> %s", (code.upper(), guest_id))
    if not referrer:
        return False
    await db.query(
        "UPDATE guests SET referred_by = %s, reg_source = 'referral' WHERE id = %s AND referred_by IS NULL RETURNING id",
        (referrer["id"], guest_id),
    )
    return True


# ---------- витрина клиентов и фильтры ----------

CLIENTS_CTE = f"""
WITH clients AS (
    SELECT g.id, g.name, g.surname, g.phone, g.gender, g.birth_date,
           date_part('year', age(g.birth_date))::int AS age,
           g.loyalty_points AS bonus_balance, g.card_level, g.reg_source, g.reg_channel, g.referral_code,
           g.created_at AS registered_at,
           COALESCE((SELECT -sum(t.delta) FROM bonus_tx t WHERE t.guest_id = g.id AND t.kind = 'redeem'), 0) AS bonus_spent,
           (SELECT count(*) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed') AS purchases,
           (SELECT COALESCE(round(avg({REVENUE})), 0) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed') AS avg_check,
           (SELECT COALESCE(sum({REVENUE}), 0) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed'
               AND b.starts_at >= %(from)s AND b.starts_at < %(to)s) AS revenue,
           (SELECT count(*) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed'
               AND b.starts_at >= %(from)s AND b.starts_at < %(to)s) AS checks,
           (SELECT min(b.starts_at) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed') AS first_purchase,
           (SELECT max(b.starts_at) FROM bookings b WHERE b.guest_id = g.id AND b.status = 'completed') AS last_purchase,
           EXISTS (SELECT 1 FROM consents c WHERE c.guest_id = g.id AND c.kind = 'ads' AND c.granted
                   AND c.created_at = (SELECT max(created_at) FROM consents c2 WHERE c2.guest_id = g.id AND c2.kind = 'ads'))
               AND NOT g.unsubscribed AS ads_ok,
           COALESCE((SELECT string_agg(s.segment, ',') FROM guest_segments s WHERE s.guest_id = g.id), '') AS segments
    FROM guests g WHERE g.phone IS NOT NULL AND g.deleted_at IS NULL
)
"""

# Поле фильтра → (выражение, тип). Названия — как в интерфейсе рассылок.
FIELDS = {
    "name": ("c.name", "text", "Имя"),
    "phone": ("c.phone", "text", "Телефон"),
    "gender": ("c.gender", "text", "Пол"),
    "age": ("c.age", "number", "Возраст"),
    "birth_date": ("c.birth_date", "date", "Дата рождения"),
    "bonus_balance": ("c.bonus_balance", "number", "Количество бонусов"),
    "bonus_spent": ("c.bonus_spent", "number", "Списано бонусов"),
    "purchases": ("c.purchases", "number", "Покупок (визитов)"),
    "avg_check": ("c.avg_check", "number", "Средний чек"),
    "revenue": ("c.revenue", "number", "Выручка за период"),
    "checks": ("c.checks", "number", "Чеков за период"),
    "first_purchase": ("c.first_purchase::date", "date", "Дата первой покупки"),
    "last_purchase": ("c.last_purchase::date", "date", "Дата последней покупки"),
    "reg_source": ("c.reg_source", "text", "Источник регистрации"),
    "reg_channel": ("c.reg_channel", "text", "Мессенджер"),
    "card_level": ("c.card_level", "text", "Уровень карты"),
    "segments": ("c.segments", "text", "Сегменты"),
}
OPERATORS = {
    "eq": "соответствует", "neq": "не соответствует", "contains": "содержит", "not_contains": "не содержит",
    "gt": "больше", "lt": "меньше", "filled": "заполнено", "empty": "не заполнено",
}


def condition(i: int, flt: dict, params: dict) -> str:
    field, op = flt.get("field"), flt.get("op")
    if field not in FIELDS or op not in OPERATORS:
        raise ValueError("Неизвестное условие фильтра")
    expr, kind, _ = FIELDS[field]
    key = f"f{i}"
    if op == "filled":
        return f"({expr} IS NOT NULL AND {expr}::text <> '' AND {expr}::text <> '0')"
    if op == "empty":
        return f"({expr} IS NULL OR {expr}::text = '' OR {expr}::text = '0')"
    value = str(flt.get("value", "")).strip()
    if not value:
        return "TRUE"  # незаполненное условие не сужает выборку
    if op in ("contains", "not_contains"):
        params[key] = f"%{value}%"
        neg = "NOT " if op == "not_contains" else ""
        return f"COALESCE({expr}::text, '') {neg}ILIKE %({key})s"
    params[key] = float(value) if kind == "number" else value
    cast = "::date" if kind == "date" else ""
    sign = {"eq": "=", "neq": "<>", "gt": ">", "lt": "<"}[op]
    lhs = expr if kind != "text" else f"lower({expr})"
    rhs = f"%({key})s{cast}" if kind != "text" else f"lower(%({key})s)"
    return f"{lhs} {sign} {rhs}"


def period(date_from: date | None, date_to: date | None) -> dict:
    start = datetime.combine(date_from or date(2000, 1, 1), datetime.min.time(), tzinfo=config.TZ)
    end = datetime.combine((date_to or date(2100, 1, 1)) + timedelta(days=1), datetime.min.time(), tzinfo=config.TZ)
    return {"from": start, "to": end}


async def clients(filters: list[dict] | None = None, date_from: date | None = None, date_to: date | None = None,
                  only_ads: bool = False, limit: int = 500, match: str = "all") -> list[dict]:
    params = period(date_from, date_to)
    conditions = [condition(i, f, params) for i, f in enumerate(filters or [])]
    where = ["(" + (" OR " if match == "any" else " AND ").join(conditions) + ")"] if conditions else []
    if only_ads:
        where.append("c.ads_ok")
    sql = CLIENTS_CTE + "SELECT * FROM clients c" + (" WHERE " + " AND ".join(where) if where else "")
    sql += f" ORDER BY c.revenue DESC, c.name LIMIT {int(limit)}"
    return await db.query(sql, params)


async def client(guest_id: int) -> dict | None:
    params = period(None, None) | {"gid": guest_id}
    return await db.query_one(CLIENTS_CTE + "SELECT * FROM clients c WHERE c.id = %(gid)s", params)


# ---------- аналитика ----------

def _age_group(age: int | None) -> str | None:
    if age is None:
        return None
    for lo, hi in AGE_GROUPS:
        if lo <= age <= hi:
            return f"{lo}–{hi}"
    return None


async def analytics(date_from: date | None = None, date_to: date | None = None) -> dict:
    rows = await clients(None, date_from, date_to, limit=100000)
    groups = [f"{lo}–{hi}" for lo, hi in AGE_GROUPS]
    total = len(rows) or 1
    demo = {g: {"f": 0, "m": 0} for g in groups}
    revenue = {g: {"f": 0, "m": 0} for g in groups}
    for r in rows:
        group = _age_group(r["age"])
        if group and r["gender"] in ("f", "m"):
            demo[group][r["gender"]] += 1
            revenue[group][r["gender"]] += int(r["revenue"])
    return {
        "total": len(rows),
        "new": sum(1 for r in rows if r["registered_at"] >= period(date_from, date_to)["from"]),
        "age_gender": [{"group": g, "f": demo[g]["f"] * 100 / total, "m": demo[g]["m"] * 100 / total} for g in groups],
        "revenue_age_gender": [{"group": g, **revenue[g]} for g in groups],
        "age_counts": [{"group": g, "n": demo[g]["f"] + demo[g]["m"]} for g in groups],
        "gender": _counts(rows, "gender"),
        "channels": _counts(rows, "reg_channel"),
        "sources": _counts(rows, "reg_source"),
        "bonus": await bonus_stats(date_from, date_to),
        "referral": _referral_stats(rows),
        "effectiveness": _effectiveness(rows),
    }


def _counts(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        value = r[key] or "—"
        out[value] = out.get(value, 0) + 1
    return out


async def bonus_stats(date_from: date | None, date_to: date | None) -> dict:
    p = period(date_from, date_to)
    row = await db.query_one(
        """SELECT COALESCE(sum(delta) FILTER (WHERE kind IN ('accrual', 'gift', 'referral')), 0) AS accrued,
                  COALESCE(-sum(delta) FILTER (WHERE kind = 'redeem'), 0) AS redeemed,
                  COALESCE(-sum(delta) FILTER (WHERE kind = 'expire'), 0) AS expired
           FROM bonus_tx WHERE created_at >= %(from)s AND created_at < %(to)s""",
        p,
    )
    sales = await db.query_one(
        f"""SELECT COALESCE(sum({REVENUE}), 0) AS paid, COALESCE(sum(b.bonus_spent), 0) AS bonus
            FROM bookings b WHERE b.status = 'completed' AND b.starts_at >= %(from)s AND b.starts_at < %(to)s""",
        p,
    )
    accrued = row["accrued"] or 0
    gross = (sales["paid"] or 0) + (sales["bonus"] or 0)
    return {
        "accrued": accrued,
        "redeemed": row["redeemed"],
        "expired": row["expired"],
        "redeem_rate": row["redeemed"] / accrued if accrued else 0,
        "burn_rate": row["expired"] / accrued if accrued else 0,
        "avg_discount_pct": (sales["bonus"] or 0) * 100 / gross if gross else 0,
    }


def _referral_stats(rows: list[dict]) -> dict:
    invited = [r for r in rows if r["reg_source"] == "referral"]
    return {"invited": len(invited), "revenue": sum(int(r["revenue"]) for r in invited)}


def _effectiveness(rows: list[dict]) -> dict:
    participants = len(rows)
    active = [r for r in rows if r["checks"] > 0]
    total_revenue = sum(int(r["revenue"]) for r in rows)
    return {
        "participants": participants,
        "active": len(active),
        "no_purchases": sum(1 for r in rows if r["purchases"] == 0),
        "regularity": sum(r["checks"] for r in active) / len(active) if active else 0,
        "revenue_total": total_revenue,
        "revenue_per_participant": total_revenue / participants if participants else 0,
        "revenue_per_active": total_revenue / len(active) if active else 0,
    }
