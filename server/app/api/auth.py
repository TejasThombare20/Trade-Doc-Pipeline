"""Sign-in / sign-out endpoints.

No real auth in Part 1 — the sign-in picks a tenant and role, no password.
The session is a JWT stored in an httpOnly cookie so SSE (EventSource, which
cannot send custom headers) authenticates automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_tenant_context
from app.core.auth import issue_token
from app.core.config import get_settings
from app.core.errors import ValidationError
from app.db.pool import get_pool
from app.repositories import tenants as tenant_repo
from app.schemas.api import SessionInfo, SignInRequest, TenantContext, TenantOption

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/tenants", response_model=list[TenantOption])
async def list_tenants():
    """Public: tenants to choose from on the sign-in screen."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await tenant_repo.list_tenants(conn)
    return [TenantOption(id=r["id"], name=r["name"], slug=r["slug"]) for r in rows]


@router.post("/session", response_model=SessionInfo)
async def sign_in(req: SignInRequest, response: Response):
    settings = get_settings()
    pool = get_pool()
    async with pool.acquire() as conn:
        tenant = await tenant_repo.get_tenant_by_slug(conn, req.tenant_slug)
    if tenant is None:
        raise ValidationError(f"unknown tenant slug: {req.tenant_slug}")

    token, session_id = issue_token(
        tenant_id=str(tenant["id"]),
        tenant_name=tenant["name"],
        tenant_slug=tenant["slug"],
        role=req.role.value,
    )
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=(settings.ENV == "prod"),
        path="/",
    )
    return SessionInfo(
        tenant_id=tenant["id"],
        tenant_name=tenant["name"],
        tenant_slug=tenant["slug"],
        role=req.role,
        session_id=session_id,
    )


@router.post("/signout")
async def sign_out(response: Response):
    settings = get_settings()
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
    )
    return {"ok": True}


@router.get("/me", response_model=SessionInfo)
async def me(ctx: TenantContext = Depends(get_tenant_context)):
    return SessionInfo(
        tenant_id=ctx.tenant_id,
        tenant_name=ctx.tenant_name,
        tenant_slug=ctx.tenant_slug,
        role=ctx.role,
        session_id=ctx.session_id,
    )
