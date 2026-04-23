"""Translate domain exceptions into structured JSON HTTP errors."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error",
        extra={
            "code": exc.code,
            "error_message": exc.message,
            "path": request.url.path,
            "details": exc.details,
        },
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_error",
        extra={"path": request.url.path, "error_type": type(exc).__name__, "error_detail": str(exc)},
    )
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": "Internal server error", "details": {}},
    )
