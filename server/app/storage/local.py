"""Local-disk storage. Used in dev; writes under <LOCAL_STORAGE_ROOT>/<key>."""

from __future__ import annotations

from pathlib import Path

import aiofiles
import aiofiles.os

from app.storage.base import Storage, StoredObject


class LocalStorage:
    backend_name = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Guard against path traversal: keys must be relative and segment-safe.
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError(f"invalid storage key: {key}")
        return self._root / key

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        path = self._resolve(key)
        await aiofiles.os.makedirs(path.parent, exist_ok=True)
        async with aiofiles.open(path, "wb") as fh:
            await fh.write(data)
        return StoredObject(key=key, size_bytes=len(data), backend=self.backend_name)

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        async with aiofiles.open(path, "rb") as fh:
            return await fh.read()

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            await aiofiles.os.remove(path)
        except FileNotFoundError:
            return

    async def exists(self, key: str) -> bool:
        path = self._resolve(key)
        return await aiofiles.os.path.exists(path)
