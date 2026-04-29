"""Job repository — DB access for the Job entity (multi-document upload bundle)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import asyncpg


JobStatus = Literal["pending", "processing", "completed", "partial_failure", "failed"]


class JobRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_job(
        self,
        *,
        tenant_id: UUID,
        rule_book_id: UUID,
        document_count: int,
    ) -> asyncpg.Record:
        return await self._conn.fetchrow(
            """
            INSERT INTO jobs (tenant_id, rule_book_id, status, document_count)
            VALUES ($1, $2, 'pending', $3)
            RETURNING id, tenant_id, rule_book_id, status, document_count,
                      is_active, started_at, completed_at, created_at, updated_at
            """,
            tenant_id, rule_book_id, document_count,
        )

    async def get_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tenant_id, rule_book_id, status, document_count,
                   is_active, started_at, completed_at, created_at, updated_at
            FROM jobs
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, job_id,
        )

    async def list_jobs(
        self,
        *,
        tenant_id: UUID,
        limit: int = 200,
    ) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT id, tenant_id, rule_book_id, status, document_count,
                   is_active, started_at, completed_at, created_at, updated_at
            FROM jobs
            WHERE tenant_id = $1 AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT $2
            """,
            tenant_id, limit,
        )

    async def update_status(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        status: JobStatus,
        mark_started: bool = False,
        mark_completed: bool = False,
    ) -> None:
        await self._conn.execute(
            f"""
            UPDATE jobs
            SET status = $3,
                started_at = CASE WHEN $4 THEN COALESCE(started_at, now()) ELSE started_at END,
                completed_at = CASE WHEN $5 THEN now() ELSE completed_at END,
                updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, job_id, status, mark_started, mark_completed,
        )

    async def soft_delete(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> None:
        """Soft-delete the job and cascade is_active=false to its documents."""
        async with self._conn.transaction():
            await self._conn.execute(
                """
                UPDATE jobs SET is_active = FALSE, updated_at = now()
                WHERE tenant_id = $1 AND id = $2
                """,
                tenant_id, job_id,
            )
            await self._conn.execute(
                """
                UPDATE documents SET is_active = FALSE, updated_at = now()
                WHERE tenant_id = $1 AND job_id = $2
                """,
                tenant_id, job_id,
            )

    async def list_documents_for_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT id, original_name, session_id, type, doc_type,
                   status, is_active, mime_type, size_bytes, storage_key,
                   created_at, updated_at
            FROM documents
            WHERE tenant_id = $1 AND job_id = $2
            ORDER BY created_at ASC
            """,
            tenant_id, job_id,
        )

    async def recompute_status_from_documents(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> JobStatus:
        """Roll up child document statuses into a single job status, persist, return it.

        Rules:
          - all documents 'completed'                 → completed
          - all documents 'failed'                    → failed
          - mix of completed + failed (none in flight) → partial_failure
          - any in flight (uploaded/preprocessing/extracting/validating/deciding) → processing
          - none touched yet (all 'uploaded' before /start) → pending
        """
        rows = await self._conn.fetch(
            """
            SELECT status FROM documents
            WHERE tenant_id = $1 AND job_id = $2
            """,
            tenant_id, job_id,
        )
        statuses = [r["status"] for r in rows]
        in_flight = {"preprocessing", "extracting", "validating", "deciding"}
        completed_count = sum(1 for s in statuses if s == "completed")
        failed_count = sum(1 for s in statuses if s == "failed")
        in_flight_count = sum(1 for s in statuses if s in in_flight)
        uploaded_count = sum(1 for s in statuses if s == "uploaded")
        total = len(statuses)

        new_status: JobStatus
        mark_started = False
        mark_completed = False
        if total == 0:
            new_status = "pending"
        elif in_flight_count > 0 or (uploaded_count > 0 and (completed_count > 0 or failed_count > 0)):
            new_status = "processing"
            mark_started = True
        elif completed_count == total:
            new_status = "completed"
            mark_started = True
            mark_completed = True
        elif failed_count == total:
            new_status = "failed"
            mark_started = True
            mark_completed = True
        elif completed_count > 0 and failed_count > 0 and in_flight_count == 0 and uploaded_count == 0:
            new_status = "partial_failure"
            mark_started = True
            mark_completed = True
        else:
            new_status = "pending"

        await self.update_status(
            tenant_id=tenant_id,
            job_id=job_id,
            status=new_status,
            mark_started=mark_started,
            mark_completed=mark_completed,
        )
        return new_status
