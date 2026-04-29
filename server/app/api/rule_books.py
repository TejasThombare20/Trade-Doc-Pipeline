"""Admin-only rule book upload + listing.

Listing returns only metadata (no extracted_rules). For the full rule list
use GET /v1/rule-books/{document_id}.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import get_document_repo, get_rule_book_svc, require_admin, get_tenant_context
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.repositories.documents import DocumentRepository
from app.schemas.api import RuleBookBundle, RuleBookUploadResponse, StoredDocumentMeta, TenantContext
from app.services.rule_books import RuleBookService

router = APIRouter(prefix="/v1/rule-books", tags=["rule-books"])


def _file_url(document_id) -> str:
    return f"/v1/files/{document_id}"


@router.post("/upload")
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
    upload_response = RuleBookUploadResponse(
        document_id=res["document_id"],
        session_id=res["session_id"],
        status=res["status"],
    )
    return JSONResponse(
        status_code=200,
        content={"data": upload_response.model_dump(mode="json"), "message": "Rule book uploaded successfully", "statusCode": 200},
    )


@router.get("")
async def list_rule_books(
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
):
    """List rule books with metadata only — no extracted_rules in this response.

    Use GET /v1/rule-books/{id} for the full rule list.
    """
    rows = await repo.list_rule_books(tenant_id=ctx.tenant_id)
    result: list[RuleBookBundle] = []
    for r in rows:
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
            file_url=_file_url(r["id"]),
        )
        result.append(RuleBookBundle(document=doc_meta, extracted_rules=None))
    return JSONResponse(
        status_code=200,
        content={"data": [rb.model_dump(mode="json") for rb in result], "message": "Rule books fetched successfully", "statusCode": 200},
    )


@router.get("/{document_id}")
async def get_rule_book(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
):
    """Full rule book detail including extracted rules (read from extractions table)."""
    from uuid import UUID
    doc_uuid = UUID(document_id)
    doc = await repo.get_document(tenant_id=ctx.tenant_id, document_id=doc_uuid)
    if doc is None or doc["type"] != "rule_book":
        raise NotFoundError("rule book not found")

    rules_raw = await repo.get_rule_book_rules(
        tenant_id=ctx.tenant_id, document_id=doc_uuid,
    )

    doc_meta = StoredDocumentMeta(
        id=doc["id"],
        tenant_id=doc["tenant_id"],
        session_id=doc["session_id"],
        type="rule_book",
        original_name=doc["original_name"],
        mime_type=doc["mime_type"],
        size_bytes=doc["size_bytes"],
        doc_type=None,
        status=doc["status"],
        is_active=doc["is_active"],
        created_at=doc["created_at"],
        file_url=_file_url(doc["id"]),
    )
    bundle = RuleBookBundle(document=doc_meta, extracted_rules=rules_raw)
    return JSONResponse(
        status_code=200,
        content={"data": bundle.model_dump(mode="json"), "message": "Rule book fetched successfully", "statusCode": 200},
    )
