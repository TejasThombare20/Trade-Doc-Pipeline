"""Rule-book upload orchestration."""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from uuid import UUID

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.db.pool import DbPool, get_db_pool
from app.repositories.documents import DocumentRepository
from app.services.pipeline import PipelineService, get_pipeline_service
from app.storage import get_storage
from app.storage.factory import build_rule_book_key

logger = get_logger(__name__)

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class RuleBookService:
    def __init__(self, db_pool: DbPool, pipeline: PipelineService) -> None:
        self._pool = db_pool
        self._pipeline = pipeline

    async def upload_rule_book(
        self,
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

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                repo = DocumentRepository(conn)
                await repo.create_document(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    type="rule_book",
                    storage_key=storage_key,
                    original_name=filename,
                    mime_type=mime,
                    size_bytes=len(data),
                )
                session_id = await repo.create_pipeline_session(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    type="rule_book",
                )
                await repo.set_document_session(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    session_id=session_id,
                )

        asyncio.create_task(self._run_rule_book_task(
            tenant_id=tenant_id,
            document_id=document_id,
            session_id=session_id,
            storage_key=storage_key,
            mime_type=mime,
            original_name=filename,
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
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        session_id: UUID,
        storage_key: str,
        mime_type: str,
        original_name: str,
    ) -> None:
        try:
            await self._pipeline.run_rule_book_pipeline(
                tenant_id=tenant_id,
                document_id=document_id,
                session_id=session_id,
                storage_key=storage_key,
                mime_type=mime_type,
                original_name=original_name,
            )
        except Exception:
            logger.exception("rule_book_pipeline_crashed")
            async with self._pool.acquire() as conn:
                repo = DocumentRepository(conn)
                await repo.complete_pipeline_session(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    status="fail",
                    total_tokens_in=0,
                    total_tokens_out=0,
                    error_message="pipeline_crashed",
                )


# Module-level singleton
_rule_book_service: RuleBookService | None = None


def get_rule_book_service() -> RuleBookService:
    global _rule_book_service
    if _rule_book_service is None:
        _rule_book_service = RuleBookService(
            db_pool=get_db_pool(),
            pipeline=get_pipeline_service(),
        )
    return _rule_book_service


# Backward-compat module-level function
async def upload_rule_book(
    *,
    tenant_id: UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict:
    return await get_rule_book_service().upload_rule_book(
        tenant_id=tenant_id,
        filename=filename,
        content_type=content_type,
        data=data,
    )
