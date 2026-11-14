"""Гости: идентификация по MAX, телефон и карта лояльности, согласия, история диалога, состояние сессии."""
import json
import re

from . import config, db

MERGE_STATEMENTS = (
    "UPDATE bookings SET guest_id = %s WHERE guest_id = %s",
    "UPDATE messages SET guest_id = %s WHERE guest_id = %s",
    "UPDATE consents SET guest_id = %s WHERE guest_id = %s",
    "UPDATE escalations SET guest_id = %s WHERE guest_id = %s",
    "UPDATE outbox SET guest_id = %s WHERE guest_id = %s",
)
PHONE_RE =re.compile(r"(?:\+7|8|7)?[\s\-(]*(\d{3})[\s\-)]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})")


def normalize_phone(raw: str) -> str | None:
    match = PHONE_RE.search(raw or "")
    if not match:
        return None
    return "+7" + "".join(match.groups())


async def by_channel(user_id: int, name: str | None = None, chat_id: int | None = None) -> dict:
    """Гость по идентификатору пользователя MAX (или веб-эмулятора). Создаётся при первом обращении."""
    async with db.tx() as conn:
        guest = await db.fetchone(conn, "SELECT * FROM guests WHERE max_user_id = %s", (user_id,))
        if guest:
            if chat_id and guest["max_chat_id"] != chat_id:
                await conn.execute("UPDATE guests SET max_chat_id = %s WHERE id = %s", (chat_id, guest["id"]))
            return guest
        return await db.fetchone(
            conn,
            "INSERT INTO guests (max_user_id, max_chat_id, name) VALUES (%s, %s, %s) RETURNING *",
            (user_id, chat_id, name),
        )


async def get(guest_id: int) -> dict:
    return await db.query_one("SELECT * FROM guests WHERE id = %s", (guest_id,))


async def attach_phone(guest_id: int, phone: str) -> dict:
    """Привязывает телефон. Если гость с таким телефоном уже есть в базе — объединяет записи."""
    async with db.tx() as conn:
        known = await db.fetchone(conn, "SELECT * FROM guests WHERE phone = %s AND id <> %s", (phone, guest_id))
        if not known:
            return await db.fetchone(
                conn,
                """UPDATE guests SET phone = %s,
                       loyalty_card = COALESCE(loyalty_card, 'SP-' || (200000 + id))
                   WHERE id = %s RETURNING *""",
                (phone, guest_id),
            )
        current = await db.fetchone(conn, "SELECT * FROM guests WHERE id = %s", (guest_id,))
        for sql in MERGE_STATEMENTS:
            await conn.execute(sql, (known["id"], guest_id))
        await conn.execute("DELETE FROM sessions WHERE guest_id = %s", (known["id"],))
        await conn.execute("UPDATE sessions SET guest_id = %s WHERE guest_id = %s", (known["id"], guest_id))
        await conn.execute("UPDATE guests SET max_user_id = NULL WHERE id = %s", (guest_id,))
        merged = await db.fetchone(
            conn,
            """UPDATE guests SET max_user_id = %s, max_chat_id = %s, lang = %s, name = COALESCE(name, %s)
               WHERE id = %s RETURNING *""",
            (current["max_user_id"], current["max_chat_id"], current["lang"], current["name"], known["id"]),
        )
        await conn.execute("DELETE FROM guests WHERE id = %s", (guest_id,))
        return merged


async def set_lang(guest_id: int, lang: str) -> None:
    await db.query("UPDATE guests SET lang = %s WHERE id = %s RETURNING id", (lang, guest_id))


async def has_consent(guest_id: int, kind: str) -> bool:
    row = await db.query_one(
        "SELECT granted FROM consents WHERE guest_id = %s AND kind = %s ORDER BY created_at DESC LIMIT 1",
        (guest_id, kind),
    )
    return bool(row and row["granted"])


async def add_consent(guest_id: int, kind: str, granted: bool, channel: str = "max") -> None:
    await db.query(
        "INSERT INTO consents (guest_id, kind, granted, text_version, channel) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (guest_id, kind, granted, config.CONSENT_VERSION, channel),
    )


async def log(guest_id: int, role: str, text: str) -> None:
    await db.query(
        "INSERT INTO messages (guest_id, role, text) VALUES (%s, %s, %s) RETURNING id", (guest_id, role, text[:4000])
    )


async def history(guest_id: int, limit: int = 50) -> list[dict]:
    rows = await db.query(
        "SELECT role, text, created_at FROM messages WHERE guest_id = %s ORDER BY id DESC LIMIT %s", (guest_id, limit)
    )
    return list(reversed(rows))


async def get_state(guest_id: int) -> dict:
    row = await db.query_one("SELECT state, misunderstood FROM sessions WHERE guest_id = %s", (guest_id,))
    if not row:
        return {"misunderstood": 0}
    return {**row["state"], "misunderstood": row["misunderstood"]}


async def save_state(guest_id: int, state: dict) -> None:
    data = {k: v for k, v in state.items() if k != "misunderstood"}
    await db.query(
        """INSERT INTO sessions (guest_id, state, misunderstood, updated_at) VALUES (%s, %s, %s, now())
           ON CONFLICT (guest_id) DO UPDATE SET state = EXCLUDED.state,
               misunderstood = EXCLUDED.misunderstood, updated_at = now()
           RETURNING guest_id""",
        (guest_id, json.dumps(data, ensure_ascii=False), state.get("misunderstood", 0)),
    )
