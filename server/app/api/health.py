"""Health check."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_conn

router = APIRouter(tags=["health"])


@router.get("/v1/health")
async def health(conn=Depends(get_conn)):
    await conn.execute("SELECT 1")
    return JSONResponse(
        status_code=200,
        content={"data": {"status": "ok"}, "message": "Service is healthy", "statusCode": 200},
    )
