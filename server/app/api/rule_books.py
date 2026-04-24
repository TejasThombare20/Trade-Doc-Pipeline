"""Admin-only rule book upload + listing."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_document_repo, get_rule_book_svc, require_admin, get_tenant_context
from app.core.config import get_settings
from app.core.errors import ValidationError
from app.repositories.documents import DocumentRepository
from app.schemas.api import RuleBookBundle, RuleBookUploadResponse, StoredDocumentMeta, TenantContext
from app.services.rule_books import RuleBookService

router = APIRouter(prefix="/api/rule-books", tags=["rule-books"])


def _file_url(storage_key: str) -> str:
    return f"/api/files/{storage_key}"


@router.post("/upload", response_model=RuleBookUploadResponse)
async def upload(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_admin),
    svc: RuleBookService = Depends(get_rule_book_svc),
):
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(f"file exceeds max size {settings.MAX_UPLOAD_BYTES} bytes")

    res = await svc.upload_rule_book(
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
    repo: DocumentRepository = Depends(get_document_repo),
):
    rows = await repo.list_rule_books(tenant_id=ctx.tenant_id)
    result: list[RuleBookBundle] = []
    for r in rows:
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
        result.append(RuleBookBundle(document=doc_meta, extracted_rules=rules_raw))
    return result
