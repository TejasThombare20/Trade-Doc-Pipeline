"""Pipeline orchestration state + timeline contracts used by the UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DocumentStatus


class TimelineStep(BaseModel):
    """One row from pipeline_runs, serialized for the UI."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    step_type: str
    mode: str
    status: str
    response: dict | list | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentDetail(BaseModel):
    """Full document detail with extracted results from tool_output."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    job_id: UUID | None = None
    session_id: UUID | None
    type: Literal["document", "rule_book"]
    original_name: str
    mime_type: str
    size_bytes: int
    doc_type: str | None
    status: DocumentStatus
    is_active: bool
    created_at: datetime
    file_url: str | None = None
    extraction: dict | None = None
    validation: dict | None = None
    decision: dict | None = None
    pipeline_status: str | None = None
    total_tokens_in: int = 0
    total_tokens_out: int = 0


