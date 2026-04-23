"""Serve uploaded files by storage key.

The frontend can't read local paths directly, so the backend serves them
at /api/files/<storage_key>. For S3, we could redirect to a presigned URL,
but for simplicity (and local dev) we just stream the bytes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_tenant_context
from app.core.errors import NotFoundError
from app.schemas.api import TenantContext
from app.storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{storage_key:path}")
async def get_file(
    storage_key: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Serve an uploaded file by its storage key.

    The tenant check ensures the key belongs to their namespace (storage keys
    are prefixed with tenant_id). This is a simple check for Part 1.
    """
    # Basic tenant isolation: storage keys start with "documents/<tenant>" or "rule_books/<tenant>"
    tenant_str = str(ctx.tenant_id)
    if tenant_str not in storage_key:
        raise NotFoundError("file not found")

    storage = get_storage()
    try:
        data = await storage.get(storage_key)
    except Exception:
        raise NotFoundError("file not found")

    # Guess content type from the key extension
    import mimetypes
    content_type = mimetypes.guess_type(storage_key)[0] or "application/octet-stream"

    return Response(content=data, media_type=content_type)
