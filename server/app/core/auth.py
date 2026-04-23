"""JWT helpers for tenant-level sessions.

Part 1 has no user schema: a session identifies a tenant + role. The JWT
carries tenant_id, tenant_name, slug, role, and session_id (random per login
so signout invalidates only this session — though since we don't keep a
server-side allowlist in Part 1, signout is effectively just a cookie clear).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.errors import AuthError


def issue_token(
    *,
    tenant_id: str,
    tenant_name: str,
    tenant_slug: str,
    role: str,
) -> tuple[str, str]:
    """Return (jwt, session_id). session_id is the jti claim."""
    settings = get_settings()
    session_id = uuid.uuid4().hex
    now = int(time.time())
    payload: dict[str, Any] = {
        "iat": now,
        "exp": now + settings.SESSION_TTL_SECONDS,
        "jti": session_id,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_slug": tenant_slug,
        "role": role,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, session_id


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("invalid session") from exc
