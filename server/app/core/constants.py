"""Application-wide constants."""

from __future__ import annotations

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

ALLOWED_MIME_DISPLAY = "PDF, JPEG, PNG, WEBP, DOCX"
