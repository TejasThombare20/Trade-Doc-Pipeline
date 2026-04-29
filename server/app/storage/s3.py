"""S3 storage backend using aioboto3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aioboto3
from botocore.exceptions import ClientError

from app.storage.base import SignedUrl, Storage, StoredObject


class S3Storage:
    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._endpoint_url = endpoint_url

    def _client(self):
        return self._session.client("s3", endpoint_url=self._endpoint_url)

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return StoredObject(key=key, size_bytes=len(data), backend=self.backend_name)

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise FileNotFoundError(key) from e
                raise
            async with resp["Body"] as stream:
                return await stream.read()

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
                    return False
                raise

    async def get_url(self, key: str, *, expiry_hours: int = 1) -> SignedUrl:
        """Generate a presigned GET URL for the S3 object."""
        expiry_secs = expiry_hours * 3600
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiry_secs,
            )
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=expiry_hours)
        return SignedUrl(url=url, expires_at=expires_at)
