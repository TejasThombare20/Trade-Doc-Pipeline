"""Job orchestration: bundle multiple uploads, then run pipelines sequentially.

A Job groups N trade documents that the user uploaded together. The rule
book in effect at job-creation time is snapshotted onto the job so that
toggling the active rule book later cannot change a job mid-flight.

Flow:
  1. POST /v1/documents (multipart, N files)  → create_job_with_documents()
     - validates tenant has an active rule book
     - creates job (status=pending), uploads all N files to storage,
       writes N document rows (status=uploaded), all linked to the job
  2. POST /v1/jobs/{id}/start                  → start_job()
     - sets job status=processing
     - runs pipeline for each document sequentially (one-by-one)
     - when all docs reach a terminal status, rolls up to
       completed / partial_failure / failed
"""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from uuid import UUID

from app.core.constants import ALLOWED_MIME_DISPLAY, ALLOWED_MIME_TYPES
from app.core.errors import ConflictError, NotFoundError, RuleBookMissingError, ValidationError
from app.core.logging import get_logger
from app.db.pool import DbPool, get_db_pool
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import JobRepository
from app.services.pipeline import PipelineService, get_pipeline_service
from app.storage import get_storage
from app.storage.factory import build_document_key

logger = get_logger(__name__)


class UploadFile:
    """Lightweight container for a single in-memory file to upload."""

    __slots__ = ("filename", "content_type", "data")

    def __init__(self, filename: str, content_type: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.data = data


class JobService:
    def __init__(self, db_pool: DbPool, pipeline: PipelineService) -> None:
        self._pool = db_pool
        self._pipeline = pipeline

    # ─── creation ────────────────────────────────────────────────────────────

    async def create_job_with_documents(
        self,
        *,
        tenant_id: UUID,
        files: list[UploadFile],
    ) -> dict:
        """Validate inputs, snapshot the active rule book, persist Job + N Documents."""
        if not files:
            raise ValidationError("At least one file is required.")

        # Validate every file's mime type and size up front.
        normalized: list[tuple[UploadFile, str]] = []
        for f in files:
            if len(f.data) == 0:
                raise ValidationError(f"File '{f.filename}' is empty.")
            mime = (
                f.content_type
                or mimetypes.guess_type(f.filename)[0]
                or "application/octet-stream"
            )
            if mime not in ALLOWED_MIME_TYPES:
                raise ValidationError(
                    f"Unsupported file type for '{f.filename}'. Allowed: {ALLOWED_MIME_DISPLAY}."
                )
            normalized.append((f, mime))

        # Snapshot the active rule book — this id is bound to the job for life.
        async with self._pool.acquire() as conn:
            doc_repo = DocumentRepository(conn)
            rb = await doc_repo.get_active_rule_book(tenant_id=tenant_id)
            if rb is None:
                raise RuleBookMissingError(
                    "No active rule book found. Please upload a rule book before submitting documents."
                )
            rule_book_id = rb["id"]

        # Storage uploads happen first (durably stored), then DB writes.
        storage = get_storage()
        document_specs: list[dict] = []
        for f, mime in normalized:
            doc_id = uuid.uuid4()
            ext = Path(f.filename).suffix or _ext_from_mime(mime)
            storage_key = build_document_key(str(tenant_id), str(doc_id), ext)
            await storage.put(storage_key, f.data, content_type=mime)
            document_specs.append({
                "document_id": doc_id,
                "filename": f.filename,
                "mime": mime,
                "size": len(f.data),
                "storage_key": storage_key,
            })

        # Create Job + Documents in a single transaction.
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                job_repo = JobRepository(conn)
                doc_repo = DocumentRepository(conn)

                job_row = await job_repo.create_job(
                    tenant_id=tenant_id,
                    rule_book_id=rule_book_id,
                    document_count=len(document_specs),
                )
                job_id = job_row["id"]

                docs_out: list[dict] = []
                for spec in document_specs:
                    await doc_repo.create_document(
                        document_id=spec["document_id"],
                        tenant_id=tenant_id,
                        type="document",
                        storage_key=spec["storage_key"],
                        original_name=spec["filename"],
                        mime_type=spec["mime"],
                        size_bytes=spec["size"],
                        job_id=job_id,
                    )
                    docs_out.append({
                        "document_id": spec["document_id"],
                        "original_name": spec["filename"],
                        "mime_type": spec["mime"],
                        "size_bytes": spec["size"],
                        "status": "uploaded",
                    })

        logger.info(
            "job_created",
            extra={
                "job_id": str(job_id),
                "document_count": len(docs_out),
                "rule_book_id": str(rule_book_id),
            },
        )
        return {
            "job_id": job_id,
            "rule_book_id": rule_book_id,
            "status": "pending",
            "documents": docs_out,
        }

    # ─── start ───────────────────────────────────────────────────────────────

    async def start_job(self, *, tenant_id: UUID, job_id: UUID) -> dict:
        """Kick off sequential pipelines for every document in the job.

        Idempotent: a second call on a job that's already started returns 409.
        Returns immediately; the actual pipelines run in a background task.
        """
        async with self._pool.acquire() as conn:
            job_repo = JobRepository(conn)
            job = await job_repo.get_job(tenant_id=tenant_id, job_id=job_id)
            if job is None or not job["is_active"]:
                raise NotFoundError("job not found")
            if job["status"] != "pending":
                raise ConflictError(
                    f"Job already in status '{job['status']}'."
                )
            await job_repo.update_status(
                tenant_id=tenant_id,
                job_id=job_id,
                status="processing",
                mark_started=True,
            )
            docs = await job_repo.list_documents_for_job(
                tenant_id=tenant_id, job_id=job_id,
            )

        # Snapshot of metadata needed to run pipelines (avoid holding the conn).
        runs = [
            {
                "document_id": d["id"],
                "storage_key": d["storage_key"],
                "mime_type": d["mime_type"],
                "original_name": d["original_name"],
            }
            for d in docs
            if d["type"] == "document"
        ]

        rule_book_id = job["rule_book_id"]
        asyncio.create_task(
            self._run_job_documents(
                tenant_id=tenant_id,
                job_id=job_id,
                rule_book_id=rule_book_id,
                runs=runs,
            )
        )
        return {"job_id": job_id, "status": "processing", "document_count": len(runs)}

    async def _run_job_documents(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        rule_book_id: UUID,
        runs: list[dict],
    ) -> None:
        """Process each document sequentially; roll up job status at the end."""
        for r in runs:
            try:
                # Each document gets its own pipeline_session, created here.
                async with self._pool.acquire() as conn:
                    repo = DocumentRepository(conn)
                    session_id = await repo.create_pipeline_session(
                        tenant_id=tenant_id,
                        document_id=r["document_id"],
                        type="document",
                    )
                    await repo.set_document_session(
                        tenant_id=tenant_id,
                        document_id=r["document_id"],
                        session_id=session_id,
                    )

                await self._pipeline.run_document_pipeline(
                    tenant_id=tenant_id,
                    document_id=r["document_id"],
                    session_id=session_id,
                    storage_key=r["storage_key"],
                    mime_type=r["mime_type"],
                    original_name=r["original_name"],
                    rule_book_id=rule_book_id,
                )
            except Exception:
                logger.exception(
                    "job_document_pipeline_failed",
                    extra={"job_id": str(job_id), "document_id": str(r["document_id"])},
                )
                # Mark this document failed and continue with the next one.
                async with self._pool.acquire() as conn:
                    repo = DocumentRepository(conn)
                    await repo.update_document_status(
                        tenant_id=tenant_id,
                        document_id=r["document_id"],
                        status="failed",
                    )

        # Roll up final job status from child documents.
        async with self._pool.acquire() as conn:
            job_repo = JobRepository(conn)
            final = await job_repo.recompute_status_from_documents(
                tenant_id=tenant_id, job_id=job_id,
            )
        logger.info("job_completed", extra={"job_id": str(job_id), "status": final})

    # ─── read / delete ───────────────────────────────────────────────────────

    async def list_jobs(self, *, tenant_id: UUID) -> list[dict]:
        async with self._pool.acquire() as conn:
            job_repo = JobRepository(conn)
            rows = await job_repo.list_jobs(tenant_id=tenant_id)
        return [_job_row_to_dict(r) for r in rows]

    async def get_job_with_documents(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict:
        async with self._pool.acquire() as conn:
            job_repo = JobRepository(conn)
            doc_repo = DocumentRepository(conn)
            job = await job_repo.get_job(tenant_id=tenant_id, job_id=job_id)
            if job is None or not job["is_active"]:
                raise NotFoundError("job not found")
            docs = await job_repo.list_documents_for_job(
                tenant_id=tenant_id, job_id=job_id,
            )
            outcomes: dict[UUID, str | None] = {}
            for d in docs:
                if d["status"] != "completed":
                    outcomes[d["id"]] = None
                    continue
                dec = await doc_repo.get_latest_decision(
                    tenant_id=tenant_id, document_id=d["id"],
                )
                if dec is None:
                    outcomes[d["id"]] = None
                else:
                    to = dec["tool_output"]
                    if isinstance(to, str):
                        import json as _json
                        to = _json.loads(to)
                    outcomes[d["id"]] = (to or {}).get("outcome")

        return {
            **_job_row_to_dict(job),
            "documents": [
                {
                    "id": d["id"],
                    "original_name": d["original_name"],
                    "session_id": d["session_id"],
                    "doc_type": d["doc_type"],
                    "status": d["status"],
                    "outcome": outcomes[d["id"]],
                    "mime_type": d["mime_type"],
                    "size_bytes": d["size_bytes"],
                    "created_at": d["created_at"],
                }
                for d in docs
            ],
        }

    async def delete_job(self, *, tenant_id: UUID, job_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            job_repo = JobRepository(conn)
            job = await job_repo.get_job(tenant_id=tenant_id, job_id=job_id)
            if job is None or not job["is_active"]:
                raise NotFoundError("job not found")
            await job_repo.soft_delete(tenant_id=tenant_id, job_id=job_id)


def _job_row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "tenant_id": r["tenant_id"],
        "rule_book_id": r["rule_book_id"],
        "status": r["status"],
        "document_count": r["document_count"],
        "is_active": r["is_active"],
        "started_at": r["started_at"],
        "completed_at": r["completed_at"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _ext_from_mime(mime: str) -> str:
    return mimetypes.guess_extension(mime) or ".bin"


# Module-level singleton
_job_service: JobService | None = None


def get_job_service() -> JobService:
    global _job_service
    if _job_service is None:
        _job_service = JobService(
            db_pool=get_db_pool(),
            pipeline=get_pipeline_service(),
        )
    return _job_service
