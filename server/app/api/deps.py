"""Request-scoped dependencies: auth, repos, services."""

from __future__ import annotations

from typing import AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import Cookie, Depends

from app.core.auth import decode_token
from app.core.errors import AuthError, ForbiddenError
from app.db.pool import DbPool, get_db_pool
from app.repositories.documents import DocumentRepository
from app.repositories.tenants import TenantRepository
from app.schemas.api import TenantContext
from app.schemas.common import UserRole
from app.services.events import SessionBus, get_event_bus_service
from app.services.jobs import JobService, get_job_service
from app.services.pipeline import PipelineService, get_pipeline_service
from app.services.rule_books import RuleBookService, get_rule_book_service


# ─── auth ────────────────────────────────────────────────────────────────────

async def get_tenant_context(
    nova_session: str | None = Cookie(default=None, alias="nova_session"),
) -> TenantContext:
    if not nova_session:
        raise AuthError("not signed in")
    payload = decode_token(nova_session)
    return TenantContext(
        tenant_id=UUID(payload["tenant_id"]),
        tenant_name=payload["tenant_name"],
        tenant_slug=payload["tenant_slug"],
        role=UserRole(payload["role"]),
        session_id=payload["jti"],
    )


async def require_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    if ctx.role != UserRole.ADMIN:
        raise ForbiddenError("admin role required")
    return ctx


# ─── db connection ────────────────────────────────────────────────────────────

async def get_conn(
    pool: DbPool = Depends(get_db_pool),
) -> AsyncGenerator[asyncpg.Connection, None]:
    async with pool.acquire() as conn:
        yield conn


# ─── repositories (request-scoped) ───────────────────────────────────────────

def get_document_repo(
    conn: asyncpg.Connection = Depends(get_conn),
) -> DocumentRepository:
    return DocumentRepository(conn)


def get_tenant_repo(
    conn: asyncpg.Connection = Depends(get_conn),
) -> TenantRepository:
    return TenantRepository(conn)


# ─── services (app-scoped singletons via Depends) ────────────────────────────

def get_pipeline_svc() -> PipelineService:
    return get_pipeline_service()


def get_rule_book_svc() -> RuleBookService:
    return get_rule_book_service()


def get_job_svc() -> JobService:
    return get_job_service()


def get_bus_svc() -> SessionBus:
    return get_event_bus_service()
