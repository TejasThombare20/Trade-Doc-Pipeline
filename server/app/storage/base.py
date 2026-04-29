"""Storage protocol. Backends implement these operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Return value of a write. `key` is what callers persist in DB."""

    key: str
    size_bytes: int
    backend: str


@dataclass(frozen=True)
class SignedUrl:
    """A time-limited URL for direct client access to a stored object."""

    url: str
    expires_at: datetime  # always UTC


class Storage(Protocol):
    backend_name: str

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        """Write bytes under `key`. Returns the stored-object descriptor."""
        ...

    async def get(self, key: str) -> bytes:
        """Read bytes at `key`. Raises FileNotFoundError if absent."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the object at `key`. No-op if already gone."""
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def get_url(self, key: str, *, expiry_hours: int = 1) -> SignedUrl:
        """Return a signed/public URL valid for `expiry_hours` hours."""
        ...
