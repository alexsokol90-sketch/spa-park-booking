"""Пул соединений PostgreSQL и вспомогательные функции запросов."""
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    _pool = AsyncConnectionPool(
        config.DATABASE_URL,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row, "autocommit": False},
    )
    await _pool.open()
    await _pool.wait()


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def tx():
    """Соединение с открытой транзакцией: commit при успехе, rollback при ошибке."""
    if _pool is None:
        raise RuntimeError("Пул соединений не открыт")
    async with _pool.connection() as conn:
        async with conn.transaction():
            yield conn


async def fetch(conn: AsyncConnection, sql: str, params: Any = None) -> list[dict]:
    cur = await conn.execute(sql, params)
    return await cur.fetchall()


async def fetchone(conn: AsyncConnection, sql: str, params: Any = None) -> dict | None:
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def query(sql: str, params: Any = None) -> list[dict]:
    async with tx() as conn:
        return await fetch(conn, sql, params)


async def query_one(sql: str, params: Any = None) -> dict | None:
    async with tx() as conn:
        return await fetchone(conn, sql, params)


async def apply_schema() -> None:
    sql = (config.ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    async with tx() as conn:
        await conn.execute(sql)
