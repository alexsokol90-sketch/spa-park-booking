"""Настройки, которые задаются во время работы и переживают перезапуск (чаты администратора)."""
from . import db


async def get(key: str) -> str | None:
    row = await db.query_one("SELECT value FROM settings WHERE key = %s", (key,))
    return row["value"] if row else None


async def put(key: str, value: str) -> None:
    await db.query(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value RETURNING key""",
        (key, value),
    )
