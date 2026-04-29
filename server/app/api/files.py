"""Return a signed/public URL for a document by document_id.

For Azure Blob (private container): generates a SAS token, valid for 1 hour.
For S3: generates a presigned URL, valid for 1 hour.
For local: returns a static path under /public/.

The URL + expiry are cached in documents.file_url / file_url_expires_at.
On each request we check expiry (with a 5-minute buffer) and regenerate if needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_document_repo, get_tenant_context
from app.core.errors import NotFoundError
from app.repositories.documents import DocumentRepository
from app.schemas.api import TenantContext
from app.storage import get_storage

router = APIRouter(prefix="/v1/files", tags=["files"])

_EXPIRY_BUFFER = timedelta(minutes=5)
_SAS_EXPIRY_HOURS = 1


@router.get("/{document_id}")
async def get_file_url(
    document_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
):
    doc = await repo.get_document(tenant_id=ctx.tenant_id, document_id=document_id)
    if doc is None:
        raise NotFoundError("file not found")

    now = datetime.now(tz=timezone.utc)
    cached_url: str | None = doc["file_url"]
    cached_expires: datetime | None = doc["file_url_expires_at"]

    # Use cached URL if it's still valid (with buffer time).
    if cached_url and cached_expires:
        expires = cached_expires if cached_expires.tzinfo else cached_expires.replace(tzinfo=timezone.utc)
        if expires - now > _EXPIRY_BUFFER:
            return JSONResponse({"url": cached_url, "expires_at": expires.isoformat()})

    # Generate a fresh signed URL.
    storage = get_storage()
    try:
        signed = await storage.get_url(doc["storage_key"], expiry_hours=_SAS_EXPIRY_HOURS)
    except Exception:
        raise NotFoundError("file not found")

    # Persist URL and expiry back to DB.
    await repo.set_file_url(
        tenant_id=ctx.tenant_id,
        document_id=document_id,
        file_url=signed.url,
        file_url_expires_at=signed.expires_at,
    )

    return JSONResponse({"url": signed.url, "expires_at": signed.expires_at.isoformat()})
