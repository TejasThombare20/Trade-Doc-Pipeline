"""Rule-book upload orchestration.

Admin uploads a PDF; we persist it in the unified documents table,
run extraction in the background, then activate it (one active book per tenant).
"""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from uuid import UUID

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.db.pool import get_pool
from app.repositories import documents as doc_repo
from app.services.pipeline import run_rule_book_pipeline
from app.storage import get_storage
from app.storage.factory import build_rule_book_key

logger = get_logger(__name__)

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def upload_rule_book(
    *,
    tenant_id: UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict:
    if len(data) == 0:
        raise ValidationError("empty file")

    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if mime not in _ALLOWED_MIME:
        raise ValidationError(f"unsupported rule book mime type: {mime}")

    document_id = uuid.uuid4()
    ext = Path(filename).suffix or ".pdf"
    storage_key = build_rule_book_key(str(tenant_id), str(document_id), ext)

    storage = get_storage()
    await storage.put(storage_key, data, content_type=mime)

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await doc_repo.create_document(
                conn,
                document_id=document_id,
                tenant_id=tenant_id,
                type="rule_book",
                storage_key=storage_key,
                original_name=filename,
                mime_type=mime,
                size_bytes=len(data),
            )
            session_id = await doc_repo.create_pipeline_session(
                conn,
                tenant_id=tenant_id,
                document_id=document_id,
                type="rule_book",
            )
            await doc_repo.set_document_session(
                conn, tenant_id=tenant_id, document_id=document_id,
                session_id=session_id,
            )

    asyncio.create_task(_run_rule_book_task(
        tenant_id=tenant_id,
        document_id=document_id, session_id=session_id,
        storage_key=storage_key, mime_type=mime, original_name=filename,
    ))

    logger.info("rule_book_uploaded", extra={
        "document_id": str(document_id),
        "session_id": str(session_id),
        "mime": mime, "size_bytes": len(data),
    })

    return {
        "document_id": document_id,
        "session_id": session_id,
        "status": "uploaded",
    }


async def _run_rule_book_task(
    *,
    tenant_id: UUID,
    document_id: UUID,
    session_id: UUID,
    storage_key: str,
    mime_type: str,
    original_name: str,
) -> None:
    try:
        await run_rule_book_pipeline(
            tenant_id=tenant_id,
            document_id=document_id, session_id=session_id,
            storage_key=storage_key,
            mime_type=mime_type, original_name=original_name,
        )
    except Exception as exc:
        logger.exception("rule_book_pipeline_crashed")
        pool = get_pool()
        async with pool.acquire() as conn:
            await doc_repo.complete_pipeline_session(
                conn, tenant_id=tenant_id, session_id=session_id,
                status="fail", total_tokens_in=0, total_tokens_out=0,
                error_message=str(exc),
            )
