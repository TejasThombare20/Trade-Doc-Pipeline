"""Storage backend factory. One instance per process."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.storage.base import Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    settings = get_settings()

    if settings.STORAGE_BACKEND == "local":
        from app.storage.local import LocalStorage
        # Resolve relative to repo root (two levels up from backend/).
        root = Path(settings.LOCAL_STORAGE_ROOT)
        if not root.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            root = repo_root / root
        return LocalStorage(root=root)

    if settings.STORAGE_BACKEND == "s3":
        from app.storage.s3 import S3Storage
        return S3Storage(
            bucket=settings.S3_BUCKET,  # type: ignore[arg-type]
            region=settings.S3_REGION,  # type: ignore[arg-type]
            access_key=settings.AWS_ACCESS_KEY_ID,  # type: ignore[arg-type]
            secret_key=settings.AWS_SECRET_ACCESS_KEY,  # type: ignore[arg-type]
            endpoint_url=settings.S3_ENDPOINT_URL,
        )

    if settings.STORAGE_BACKEND == "azure_blob":
        from app.storage.azure_blob import AzureBlobStorage
        return AzureBlobStorage(
            connection_string=settings.AZURE_STORAGE_CONNECTION_STRING,  # type: ignore[arg-type]
            container=settings.AZURE_STORAGE_CONTAINER,  # type: ignore[arg-type]
        )

    raise ValueError(
        f"Unknown STORAGE_BACKEND '{settings.STORAGE_BACKEND}'. "
        "Supported values: local, s3, azure_blob"
    )


def build_document_key(tenant_id: str, document_id: str, ext: str) -> str:
    return f"documents/{tenant_id}/{document_id}{ext}"


def build_rule_book_key(tenant_id: str, rule_book_id: str, ext: str) -> str:
    return f"rule_books/{tenant_id}/{rule_book_id}{ext}"
