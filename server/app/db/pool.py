"""Async Postgres connection pool lifecycle."""

from __future__ import annotations

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=str(settings.DATABASE_URL),
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
        command_timeout=30,
    )
    logger.info("db_pool_initialized", extra={
        "min": settings.DB_POOL_MIN, "max": settings.DB_POOL_MAX,
    })
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() first.")
    return _pool
