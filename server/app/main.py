"""FastAPI application entrypoint.

Lifecycle: startup initializes config, logging, DB pool, migrations, and the
LangGraph checkpointer. Shutdown closes them in reverse order.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, documents, health, jobs, rule_books
from app.api.errors import app_error_handler, unhandled_error_handler
from app.api.files import router as files_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.migrate import run_migrations
from app.db.pool import close_pool, init_pool
from app.services.pipeline import init_pipeline, shutdown_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger = get_logger("app.main")

    logger.info("startup", extra={
        "env": settings.ENV,
        "run_env": settings.RUN_ENV,
        "storage_backend": settings.STORAGE_BACKEND,
        "cost_cap_usd": settings.COST_CAP_USD_PER_RUN,
    })

    pool = await init_pool()
    await run_migrations(pool)
    await init_pipeline()

    # Serve uploaded files in local mode so the frontend can preview them.
    if settings.RUN_ENV == "local" or settings.STORAGE_BACKEND == "local":
        from pathlib import Path
        root = Path(settings.LOCAL_STORAGE_ROOT)
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        root.mkdir(parents=True, exist_ok=True)
        app.mount("/public", StaticFiles(directory=str(root)), name="public")

    try:
        yield
    finally:
        logger.info("shutdown")
        await shutdown_pipeline()
        await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nova Trade Document Pipeline",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(jobs.router)
    app.include_router(rule_books.router)
    app.include_router(files_router)
    return app


app = create_app()
