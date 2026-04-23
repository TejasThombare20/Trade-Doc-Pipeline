"""Storage backend factory. One instance per process."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.storage.base import Storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    settings = get_settings()
    if settings.STORAGE_BACKEND == "local":
        # Resolve relative to repo root (two levels up from backend/).
        root = Path(settings.LOCAL_STORAGE_ROOT)
        if not root.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            root = repo_root / root
        return LocalStorage(root=root)

    return S3Storage(
        bucket=settings.S3_BUCKET,  # type: ignore[arg-type]
        region=settings.S3_REGION,  # type: ignore[arg-type]
        access_key=settings.AWS_ACCESS_KEY_ID,  # type: ignore[arg-type]
        secret_key=settings.AWS_SECRET_ACCESS_KEY,  # type: ignore[arg-type]
        endpoint_url=settings.S3_ENDPOINT_URL,
    )


def build_document_key(tenant_id: str, document_id: str, ext: str) -> str:
    return f"documents/{tenant_id}/{document_id}{ext}"


def build_rule_book_key(tenant_id: str, rule_book_id: str, ext: str) -> str:
    return f"rule_books/{tenant_id}/{rule_book_id}{ext}"
