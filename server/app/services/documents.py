"""Document upload + pipeline kick-off orchestration."""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from uuid import UUID

from app.core.errors import RuleBookMissingError, ValidationError
from app.core.logging import get_logger
from app.db.pool import get_pool
from app.repositories import documents as doc_repo
from app.services.pipeline import run_document_pipeline
from app.storage import get_storage
from app.storage.factory import build_document_key

logger = get_logger(__name__)

_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def upload_and_start_pipeline(
    *,
    tenant_id: UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict:
    """Persist the document, kick off the pipeline in the background, return IDs."""
    if len(data) == 0:
        raise ValidationError("empty file")

    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if mime not in _ALLOWED_MIME:
        raise ValidationError(f"unsupported mime type: {mime}")

    pool = get_pool()
    async with pool.acquire() as conn:
        active_rule_book = await doc_repo.get_active_rule_book(
            conn, tenant_id=tenant_id
        )
        if active_rule_book is None:
            raise RuleBookMissingError(
                "This tenant has no active rule book. Upload one before running documents."
            )

    document_id = uuid.uuid4()
    ext = Path(filename).suffix or _ext_from_mime(mime)
    storage_key = build_document_key(str(tenant_id), str(document_id), ext)

    storage = get_storage()
    await storage.put(storage_key, data, content_type=mime)

    async with pool.acquire() as conn:
        async with conn.transaction():
            doc_row = await doc_repo.create_document(
                conn,
                document_id=document_id,
                tenant_id=tenant_id,
                type="document",
                storage_key=storage_key,
                original_name=filename,
                mime_type=mime,
                size_bytes=len(data),
            )
            session_id = await doc_repo.create_pipeline_session(
                conn,
                tenant_id=tenant_id,
                document_id=document_id,
                type="document",
            )
            await doc_repo.set_document_session(
                conn, tenant_id=tenant_id, document_id=document_id,
                session_id=session_id,
            )

    # Fire and forget. The pipeline updates DB state as it progresses.
    asyncio.create_task(_run_pipeline_task(
        tenant_id=tenant_id, document_id=document_id,
        session_id=session_id,
        storage_key=storage_key, mime_type=mime, original_name=filename,
    ))

    logger.info("document_uploaded", extra={
        "document_id": str(document_id),
        "session_id": str(session_id),
        "size_bytes": len(data), "mime": mime,
    })

    return {
        "document_id": document_id,
        "session_id": session_id,
        "status": "uploaded",
    }


async def _run_pipeline_task(
    *,
    tenant_id: UUID, document_id: UUID,
    session_id: UUID,
    storage_key: str, mime_type: str, original_name: str,
) -> None:
    try:
        await run_document_pipeline(
            tenant_id=tenant_id,
            document_id=document_id, session_id=session_id,
            storage_key=storage_key,
            mime_type=mime_type, original_name=original_name,
        )
    except Exception as exc:
        logger.exception("pipeline_task_crashed")
        pool = get_pool()
        async with pool.acquire() as conn:
            await doc_repo.complete_pipeline_session(
                conn, tenant_id=tenant_id, session_id=session_id,
                status="fail", total_tokens_in=0, total_tokens_out=0,
                error_message=str(exc),
            )


def _ext_from_mime(mime: str) -> str:
    guess = mimetypes.guess_extension(mime)
    return guess or ".bin"
