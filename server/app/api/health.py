"""Health check."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_conn

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(conn=Depends(get_conn)) -> dict:
    await conn.execute("SELECT 1")
    return {"status": "ok"}
