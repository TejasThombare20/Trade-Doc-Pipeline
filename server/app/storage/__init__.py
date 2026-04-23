"""Storage abstraction: local filesystem for dev, S3 for prod.

Backend is chosen via the STORAGE_BACKEND env var. Callers work with a
`storage_key` string (e.g. `documents/<tenant>/<id>.pdf`); the active backend
resolves it to bytes on read and to an absolute location on write.
"""

from app.storage.base import Storage, StoredObject
from app.storage.factory import get_storage

__all__ = ["Storage", "StoredObject", "get_storage"]
