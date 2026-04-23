"""Request-scoped dependencies: cookie-based JWT session, role gating.

Session auth is tenant-level (no user schema). The sign-in endpoint mints a
JWT for a chosen tenant + role, stored in an httpOnly cookie. All other
endpoints read the cookie here.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Cookie, Depends

from app.core.auth import decode_token
from app.core.config import get_settings
from app.core.errors import AuthError, ForbiddenError
from app.schemas.api import TenantContext
from app.schemas.common import UserRole


async def tenant_context(
    _cookie: str | None = None,
) -> TenantContext:  # overridden at runtime via Depends(_read_cookie)
    raise AuthError("tenant_context must be obtained via Depends(get_tenant_context)")


def _cookie_name() -> str:
    return get_settings().SESSION_COOKIE_NAME


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
