"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.pool import get_pool

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
