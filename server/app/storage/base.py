"""Storage protocol. Backends implement these four operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Return value of a write. `key` is what callers persist in DB."""

    key: str
    size_bytes: int
    backend: str


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
