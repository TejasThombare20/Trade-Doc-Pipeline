"""Common types reused across agents and the API layer."""

from __future__ import annotations

from enum import Enum


class DocType(str, Enum):
    BILL_OF_LADING = "bill_of_lading"
    COMMERCIAL_INVOICE = "commercial_invoice"
    PACKING_LIST = "packing_list"
    CERTIFICATE_OF_ORIGIN = "certificate_of_origin"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    DECIDING = "deciding"
    COMPLETED = "completed"
    FAILED = "failed"


class FieldStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"


class OverallStatus(str, Enum):
    ALL_MATCH = "all_match"
    HAS_UNCERTAIN = "has_uncertain"
    HAS_MISMATCH = "has_mismatch"


class Outcome(str, Enum):
    AUTO_APPROVE = "auto_approve"
    HUMAN_REVIEW = "human_review"
    DRAFT_AMENDMENT = "draft_amendment"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class UserRole(str, Enum):
    ADMIN = "admin"
    DEFAULT = "default"


# Canonical field names the Extractor must return. Keeping these as a single
# constant means the validator and router can trust the key space.
REQUIRED_FIELDS: tuple[str, ...] = (
    "consignee_name",
    "hs_code",
    "port_of_loading",
    "port_of_discharge",
    "incoterms",
    "description_of_goods",
    "gross_weight",
    "invoice_number",
)
