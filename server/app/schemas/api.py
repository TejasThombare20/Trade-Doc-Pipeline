"""API request/response contracts that don't belong to a specific agent."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UserRole


class TenantContext(BaseModel):
    """Resolved from the session cookie on every request."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: UserRole
    session_id: str


class TenantOption(BaseModel):
    """One row in the sign-in page's tenant dropdown."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    slug: str


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_slug: str
    role: UserRole = UserRole.DEFAULT


class SessionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    role: UserRole
    session_id: str




class RuleBookUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    session_id: UUID
    status: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict = Field(default_factory=dict)


class StoredDocumentMeta(BaseModel):
    """Shared metadata returned for both document and rule-book rows."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    session_id: UUID | None
    type: Literal["document", "rule_book"]
    original_name: str
    mime_type: str
    size_bytes: int
    doc_type: str | None
    status: str
    is_active: bool
    created_at: datetime
    file_url: str


class RuleBookBundle(BaseModel):
    """File meta + extracted rules. List endpoints omit extracted_rules."""

    model_config = ConfigDict(extra="forbid")

    document: StoredDocumentMeta
    extracted_rules: list[dict] | None = None
