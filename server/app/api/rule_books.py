"""Admin-only rule book upload + listing.

Rule books are stored in the unified documents table with type='rule_book'.
Since tenant = customer, rule books are scoped per tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import require_admin, get_tenant_context
from app.core.config import get_settings
from app.core.errors import ValidationError
from app.db.pool import get_pool
from app.repositories import documents as doc_repo
from app.schemas.api import RuleBookBundle, RuleBookUploadResponse, StoredDocumentMeta, TenantContext
from app.services.rule_books import upload_rule_book

router = APIRouter(prefix="/api/rule-books", tags=["rule-books"])


def _file_url(storage_key: str) -> str:
    """Build a URL for the frontend to fetch the file from the backend."""
    return f"/api/files/{storage_key}"


@router.post("/upload", response_model=RuleBookUploadResponse)
async def upload(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_admin),
):
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(f"file exceeds max size {settings.MAX_UPLOAD_BYTES} bytes")

    res = await upload_rule_book(
        tenant_id=ctx.tenant_id,
        filename=file.filename or "rule_book.pdf",
        content_type=file.content_type or "application/pdf",
        data=data,
    )
    return RuleBookUploadResponse(
        document_id=res["document_id"],
        session_id=res["session_id"],
        status=res["status"],
    )


@router.get("", response_model=list[RuleBookBundle])
async def list_rule_books(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Return rule books for the current tenant, including file path + extracted rules."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await doc_repo.list_rule_books(
            conn, tenant_id=ctx.tenant_id,
        )
    result: list[RuleBookBundle] = []
    for r in rows:
        import json
        rules_raw = r["extracted_rules"]
        if isinstance(rules_raw, str):
            rules_raw = json.loads(rules_raw)
        doc_meta = StoredDocumentMeta(
            id=r["id"],
            tenant_id=r["tenant_id"],
            session_id=r["session_id"],
            type="rule_book",
            original_name=r["original_name"],
            mime_type=r["mime_type"],
            size_bytes=r["size_bytes"],
            doc_type=None,
            status=r["status"],
            is_active=r["is_active"],
            created_at=r["created_at"],
            file_url=_file_url(r["storage_key"]),
        )
        result.append(RuleBookBundle(
            document=doc_meta,
            extracted_rules=rules_raw,
        ))
    return result
