"""Async Postgres connection pool — DbPool class + module-level singleton helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DbPool:
    """Wrapper around asyncpg.Pool with lifecycle methods."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        settings = get_settings()
        self._pool = await asyncpg.create_pool(
            dsn=str(settings.DATABASE_URL),
            min_size=settings.DB_POOL_MIN,
            max_size=settings.DB_POOL_MAX,
            command_timeout=30,
        )
        logger.info("db_pool_initialized", extra={
            "min": settings.DB_POOL_MIN, "max": settings.DB_POOL_MAX,
        })

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("db_pool_closed")

    def get(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("DbPool not initialized. Call init() first.")
        return self._pool

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        pool = self.get()
        async with pool.acquire() as conn:
            yield conn


# Module-level singleton — used by lifespan and legacy call sites.
_db_pool: DbPool = DbPool()


async def init_pool() -> asyncpg.Pool:
    await _db_pool.init()
    return _db_pool.get()


async def close_pool() -> None:
    await _db_pool.close()


def get_pool() -> asyncpg.Pool:
    return _db_pool.get()


def get_db_pool() -> DbPool:
    """Return the module-level DbPool instance for dependency injection."""
    return _db_pool
