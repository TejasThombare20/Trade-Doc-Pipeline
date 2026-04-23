"""Extractor agent input/output contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DocType


class ExtractedField(BaseModel):
    """One extracted field with confidence and source grounding.

    An absent field MUST be represented with value=null, confidence=0.0,
    source_snippet=null. Never invent a value.
    """

    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(default=None, description="Raw text as it appears in the document.")
    confidence: float = Field(ge=0.0, le=1.0)
    source_snippet: str | None = Field(
        default=None,
        description="Short verbatim excerpt from the document where this value was found.",
    )


class ExtractorOutput(BaseModel):
    """What the extractor agent returns. Keys are canonical field names."""

    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    doc_type_confidence: float = Field(ge=0.0, le=1.0)
    fields: dict[str, ExtractedField]
    notes: str | None = None
