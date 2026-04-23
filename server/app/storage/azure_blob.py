"""Azure Blob Storage backend using azure-storage-blob async API.

Requires env vars:
  AZURE_STORAGE_CONNECTION_STRING — full connection string for the storage account
  AZURE_STORAGE_CONTAINER       — container name (e.g. "documents")
"""

from __future__ import annotations

from azure.storage.blob.aio import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError

from app.storage.base import StoredObject


class AzureBlobStorage:
    backend_name = "azure_blob"

    def __init__(
        self,
        *,
        connection_string: str,
        container: str,
    ) -> None:
        self._connection_string = connection_string
        self._container = container
        self._service_client: BlobServiceClient | None = None

    def _get_service_client(self) -> BlobServiceClient:
        if self._service_client is None:
            self._service_client = BlobServiceClient.from_connection_string(
                self._connection_string,
            )
        return self._service_client

    def _blob_client(self, key: str):
        svc = self._get_service_client()
        container = svc.get_container_client(self._container)
        return container.get_blob_client(key)

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        blob = self._blob_client(key)
        async with blob:
            await blob.upload_blob(
                data,
                overwrite=True,
                content_settings=_content_settings(content_type),
            )
        return StoredObject(key=key, size_bytes=len(data), backend=self.backend_name)

    async def get(self, key: str) -> bytes:
        blob = self._blob_client(key)
        async with blob:
            try:
                stream = await blob.download_blob()
                return await stream.readall()
            except ResourceNotFoundError as e:
                raise FileNotFoundError(key) from e

    async def delete(self, key: str) -> None:
        blob = self._blob_client(key)
        async with blob:
            try:
                await blob.delete_blob()
            except ResourceNotFoundError:
                return  # already gone — treat as no-op

    async def exists(self, key: str) -> bool:
        blob = self._blob_client(key)
        async with blob:
            try:
                await blob.get_blob_properties()
                return True
            except ResourceNotFoundError:
                return False


def _content_settings(content_type: str):
    """Build ContentSettings for the blob."""
    from azure.storage.blob import ContentSettings
    return ContentSettings(content_type=content_type)
