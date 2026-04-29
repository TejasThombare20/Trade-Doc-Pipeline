"""Sign-in / sign-out endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_tenant_context, get_tenant_repo
from app.core.auth import issue_token
from app.core.config import get_settings
from app.core.errors import ValidationError
from app.repositories.tenants import TenantRepository
from app.schemas.api import SessionInfo, SignInRequest, TenantContext, TenantOption

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/tenants")
async def list_tenants(repo: TenantRepository = Depends(get_tenant_repo)):
    rows = await repo.list_tenants()
    tenants = [TenantOption(id=r["id"], name=r["name"], slug=r["slug"]) for r in rows]
    return JSONResponse(
        status_code=200,
        content={"data": [t.model_dump(mode="json") for t in tenants], "message": "Tenants fetched successfully", "statusCode": 200},
    )


@router.post("/session")
async def sign_in(
    req: SignInRequest,
    repo: TenantRepository = Depends(get_tenant_repo),
):
    settings = get_settings()
    tenant = await repo.get_tenant_by_slug(req.tenant_slug)
    if tenant is None:
        raise ValidationError(f"unknown tenant slug: {req.tenant_slug}")

    token, session_id = issue_token(
        tenant_id=str(tenant["id"]),
        tenant_name=tenant["name"],
        tenant_slug=tenant["slug"],
        role=req.role.value,
    )
    session = SessionInfo(
        tenant_id=tenant["id"],
        tenant_name=tenant["name"],
        tenant_slug=tenant["slug"],
        role=req.role,
        session_id=session_id,
    )
    res = JSONResponse(
        status_code=200,
        content={"data": session.model_dump(mode="json"), "message": "Signed in successfully", "statusCode": 200},
    )
    res.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=(settings.ENV == "prod"),
        path="/",
    )
    return res


@router.post("/signout")
async def sign_out():
    settings = get_settings()
    res = JSONResponse(
        status_code=200,
        content={"data": None, "message": "Signed out successfully", "statusCode": 200},
    )
    res.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return res


@router.get("/me")
async def me(ctx: TenantContext = Depends(get_tenant_context)):
    session = SessionInfo(
        tenant_id=ctx.tenant_id,
        tenant_name=ctx.tenant_name,
        tenant_slug=ctx.tenant_slug,
        role=ctx.role,
        session_id=ctx.session_id,
    )
    return JSONResponse(
        status_code=200,
        content={"data": session.model_dump(mode="json"), "message": "Session retrieved successfully", "statusCode": 200},
    )
