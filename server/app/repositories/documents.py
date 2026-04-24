"""Document repository — all DB access for documents, sessions, runs, and results."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

import asyncpg

DocKind = Literal["document", "rule_book"]
StepType = Literal["parsing", "extraction", "validation", "decision"]
StepStatus = Literal["pending", "success", "fail"]
StepMode = Literal["manual", "llm"]
PipelineStatus = Literal["pending", "success", "fail"]


class DocumentRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    # --------------------------- documents ---------------------------

    async def create_document(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        type: DocKind,
        storage_key: str,
        original_name: str,
        mime_type: str,
        size_bytes: int,
    ) -> asyncpg.Record:
        return await self._conn.fetchrow(
            """
            INSERT INTO documents
                (id, tenant_id, type, storage_key, original_name,
                 mime_type, size_bytes, status, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'uploaded', FALSE)
            RETURNING id, tenant_id, session_id, type, storage_key,
                      original_name, mime_type, size_bytes, doc_type, status,
                      is_active, extracted_rules, created_at, updated_at
            """,
            document_id, tenant_id, type, storage_key, original_name,
            mime_type, size_bytes,
        )

    async def set_document_session(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        session_id: UUID,
    ) -> None:
        await self._conn.execute(
            """
            UPDATE documents SET session_id = $3, updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, document_id, session_id,
        )

    async def update_document_status(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        status: str,
        doc_type: str | None = None,
    ) -> None:
        await self._conn.execute(
            """
            UPDATE documents
            SET status = $3,
                doc_type = COALESCE($4, doc_type),
                updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, document_id, status, doc_type,
        )

    async def set_extracted_rules(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        rules: list[dict],
    ) -> None:
        await self._conn.execute(
            """
            UPDATE documents
            SET extracted_rules = $3::jsonb, updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, document_id, json.dumps(rules),
        )

    async def activate_rule_book(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> None:
        """Flip is_active on the winning rule_book, deactivate all others for the tenant."""
        async with self._conn.transaction():
            await self._conn.execute(
                """
                UPDATE documents SET is_active = FALSE, updated_at = now()
                WHERE tenant_id = $1
                  AND type = 'rule_book' AND id <> $2
                """,
                tenant_id, document_id,
            )
            await self._conn.execute(
                """
                UPDATE documents SET is_active = TRUE, updated_at = now()
                WHERE tenant_id = $1 AND id = $2 AND type = 'rule_book'
                """,
                tenant_id, document_id,
            )

    async def get_document(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tenant_id, session_id, type, storage_key,
                   original_name, mime_type, size_bytes, doc_type, status,
                   is_active, extracted_rules, created_at, updated_at
            FROM documents
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, document_id,
        )

    async def get_active_rule_book(
        self,
        *,
        tenant_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tenant_id, storage_key, original_name, mime_type,
                   size_bytes, status, extracted_rules, created_at
            FROM documents
            WHERE tenant_id = $1
              AND type = 'rule_book' AND is_active = TRUE AND status = 'completed'
            """,
            tenant_id,
        )

    async def list_documents(
        self,
        *,
        tenant_id: UUID,
        type: DocKind | None = None,
        limit: int = 200,
    ) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT id, original_name, session_id, type, doc_type,
                   status, is_active, created_at
            FROM documents
            WHERE tenant_id = $1
              AND ($2::text IS NULL OR type = $2::text)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            tenant_id, type, limit,
        )

    async def list_rule_books(
        self,
        *,
        tenant_id: UUID,
    ) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT id, tenant_id, session_id, original_name, mime_type,
                   size_bytes, status, is_active, extracted_rules, storage_key,
                   created_at, updated_at
            FROM documents
            WHERE tenant_id = $1 AND type = 'rule_book'
            ORDER BY created_at DESC
            """,
            tenant_id,
        )

    # --------------------------- pipeline_sessions ---------------------------

    async def create_pipeline_session(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        type: DocKind,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO pipeline_sessions (tenant_id, document_id, type, pipeline_status)
            VALUES ($1, $2, $3, 'pending')
            RETURNING id
            """,
            tenant_id, document_id, type,
        )
        return row["id"]

    async def complete_pipeline_session(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        status: PipelineStatus,
        total_tokens_in: int,
        total_tokens_out: int,
        error_message: str | None = None,
    ) -> None:
        async with self._conn.transaction():
            await self._conn.execute(
                """
                UPDATE pipeline_sessions
                SET pipeline_status = $3,
                    completed_at = now(),
                    total_tokens_in = $4,
                    total_tokens_out = $5,
                    error_message = $6,
                    updated_at = now()
                WHERE tenant_id = $1 AND id = $2
                """,
                tenant_id, session_id, status, total_tokens_in, total_tokens_out, error_message,
            )

    async def get_pipeline_session(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tenant_id, document_id, type, pipeline_status, started_at,
                   completed_at, total_tokens_in, total_tokens_out, error_message
            FROM pipeline_sessions
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, session_id,
        )

    async def get_latest_pipeline_session_for_document(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tenant_id, document_id, type, pipeline_status, started_at,
                   completed_at, total_tokens_in, total_tokens_out, error_message
            FROM pipeline_sessions
            WHERE tenant_id = $1 AND document_id = $2
            ORDER BY started_at DESC
            LIMIT 1
            """,
            tenant_id, document_id,
        )

    # --------------------------- pipeline_runs (per-step log) ---------------------------

    async def start_pipeline_run(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        document_id: UUID,
        type: DocKind,
        step_type: StepType,
        mode: StepMode,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO pipeline_runs
                (tenant_id, session_id, document_id, type, step_type, mode, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending')
            RETURNING id
            """,
            tenant_id, session_id, document_id, type, step_type, mode,
        )
        return row["id"]

    async def finish_pipeline_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
        status: StepStatus,
        response: dict | list | None,
        total_tokens_in: int | None,
        total_tokens_out: int | None,
    ) -> None:
        await self._conn.execute(
            """
            UPDATE pipeline_runs
            SET status = $3,
                response = $4::jsonb,
                total_tokens_in = $5,
                total_tokens_out = $6,
                completed_at = now(),
                updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id, run_id, status,
            json.dumps(response) if response is not None else None,
            total_tokens_in, total_tokens_out,
        )

    async def list_runs_for_session(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
    ) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT id, step_type, mode, status, response, total_tokens_in,
                   total_tokens_out, started_at, completed_at
            FROM pipeline_runs
            WHERE tenant_id = $1 AND session_id = $2
            ORDER BY started_at ASC
            """,
            tenant_id, session_id,
        )

    # --------------------------- extractions / validations / decisions ---------------------------

    async def insert_extraction(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        session_id: UUID,
        pipeline_run_id: UUID,
        tool_content: Any,
        tool_output: Any,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO extractions
                (tenant_id, document_id, session_id, pipeline_run_id, tool_content, tool_output)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING id
            """,
            tenant_id, document_id, session_id, pipeline_run_id,
            json.dumps(tool_content), json.dumps(tool_output),
        )
        return row["id"]

    async def insert_validation(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        session_id: UUID,
        pipeline_run_id: UUID,
        tool_content: Any,
        tool_output: Any,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO validations
                (tenant_id, document_id, session_id, pipeline_run_id, tool_content, tool_output)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING id
            """,
            tenant_id, document_id, session_id, pipeline_run_id,
            json.dumps(tool_content), json.dumps(tool_output),
        )
        return row["id"]

    async def insert_decision(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        session_id: UUID,
        pipeline_run_id: UUID,
        tool_content: Any,
        tool_output: Any,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO decisions
                (tenant_id, document_id, session_id, pipeline_run_id, tool_content, tool_output)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING id
            """,
            tenant_id, document_id, session_id, pipeline_run_id,
            json.dumps(tool_content), json.dumps(tool_output),
        )
        return row["id"]

    async def get_latest_extraction(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tool_content, tool_output, created_at
            FROM extractions
            WHERE tenant_id = $1 AND document_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            tenant_id, document_id,
        )

    async def get_latest_validation(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tool_content, tool_output, created_at
            FROM validations
            WHERE tenant_id = $1 AND document_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            tenant_id, document_id,
        )

    async def get_latest_decision(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            """
            SELECT id, tool_content, tool_output, created_at
            FROM decisions
            WHERE tenant_id = $1 AND document_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            tenant_id, document_id,
        )
