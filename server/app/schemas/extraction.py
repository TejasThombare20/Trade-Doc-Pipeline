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


def _absent_field() -> ExtractedField:
    return ExtractedField(value=None, confidence=0.0, source_snippet=None)


class ExtractedFields(BaseModel):
    """Explicit per-field shape so OpenAI strict-mode schemas declare real keys.

    Using dict[str, ExtractedField] collapses to an empty-object schema under
    strict mode (additionalProperties=false with no properties), which silently
    forces the model to return an empty dict. Naming each canonical field here
    keeps the model honest.
    """

    model_config = ConfigDict(extra="forbid")

    consignee_name: ExtractedField = Field(default_factory=_absent_field)
    hs_code: ExtractedField = Field(default_factory=_absent_field)
    port_of_loading: ExtractedField = Field(default_factory=_absent_field)
    port_of_discharge: ExtractedField = Field(default_factory=_absent_field)
    incoterms: ExtractedField = Field(default_factory=_absent_field)
    description_of_goods: ExtractedField = Field(default_factory=_absent_field)
    gross_weight: ExtractedField = Field(default_factory=_absent_field)
    invoice_number: ExtractedField = Field(default_factory=_absent_field)

    def as_dict(self) -> dict[str, ExtractedField]:
        return {name: getattr(self, name) for name in self.model_fields}


class ExtractorOutput(BaseModel):
    """What the extractor agent returns."""

    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    doc_type_confidence: float = Field(ge=0.0, le=1.0)
    fields: ExtractedFields = Field(default_factory=ExtractedFields)
    notes: str | None = None
