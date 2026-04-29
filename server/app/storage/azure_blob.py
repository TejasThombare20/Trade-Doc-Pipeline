"""Azure Blob Storage backend using azure-storage-blob async API.

Requires env vars:
  AZURE_STORAGE_CONNECTION_STRING — full connection string for the storage account
  AZURE_STORAGE_CONTAINER       — container name (e.g. "documents")

The container is expected to be private. File access uses SAS tokens
(Shared Access Signatures) generated on demand and cached in the DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient

from app.storage.base import SignedUrl, StoredObject


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

    async def get_url(self, key: str, *, expiry_hours: int = 1) -> SignedUrl:
        """Generate a SAS URL for the private blob, valid for `expiry_hours`."""
        from azure.storage.blob import (
            BlobSasPermissions,
            generate_blob_sas,
        )

        svc = self._get_service_client()
        # Retrieve the account name and key from the service client.
        account_name = svc.account_name
        account_key = svc.credential.account_key

        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=expiry_hours)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self._container,
            blob_name=key,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expires_at,
        )

        # Build full URL: https://<account>.blob.core.windows.net/<container>/<key>?<sas>
        url = f"https://{account_name}.blob.core.windows.net/{self._container}/{key}?{sas_token}"
        return SignedUrl(url=url, expires_at=expires_at)


def _content_settings(content_type: str):
    """Build ContentSettings for the blob."""
    from azure.storage.blob import ContentSettings
    return ContentSettings(content_type=content_type)
