"""S3-compatible object storage provider (E3).

Supports AWS S3 and any S3-compatible service (MinIO, DigitalOcean Spaces,
Backblaze B2, Cloudflare R2, etc.) through the same boto3 client.

Configuration (via environment variables or .env):
  STORAGE_PROVIDER=s3
  STORAGE_S3_BUCKET=my-bucket
  STORAGE_S3_REGION=us-east-1          # or e.g. nyc3 for DigitalOcean
  STORAGE_S3_ACCESS_KEY=AKIA…
  STORAGE_S3_SECRET_KEY=<secret>
  STORAGE_S3_ENDPOINT_URL=             # leave empty for real AWS S3;
                                       # set to e.g. https://minio.example.com
                                       # or https://nyc3.digitaloceanspaces.com

All uploads use server-side encryption (SSE-S3).  Download presigned URLs
expire in 1 hour (configurable).  The storage key becomes the S3 object key
directly, so the existing attachment naming conventions are preserved.
"""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from app.core.config import get_settings
from app.providers.storage import StorageProvider, StoredFile

logger = logging.getLogger(__name__)

_PRESIGNED_EXPIRY = 3600  # seconds


class S3StorageProvider(StorageProvider):
    """boto3-backed S3/compatible storage.

    boto3 is synchronous; each call is dispatched to the default thread-pool
    executor so that the FastAPI event loop is never blocked.
    """

    def __init__(self) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "STORAGE_PROVIDER=s3 requires 'boto3'. "
                "Install it: pip install boto3>=1.34.0"
            ) from exc

        settings = get_settings()
        kwargs: dict[str, Any] = {
            "region_name": settings.storage_s3_region or None,
            "aws_access_key_id": settings.storage_s3_access_key.get_secret_value() or None,
            "aws_secret_access_key": settings.storage_s3_secret_key.get_secret_value() or None,
        }
        if settings.storage_s3_endpoint_url:
            kwargs["endpoint_url"] = settings.storage_s3_endpoint_url

        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.storage_s3_bucket
        if not self._bucket:
            raise ValueError("STORAGE_S3_BUCKET must be set when STORAGE_PROVIDER=s3")

    @property
    def name(self) -> str:
        return "s3"

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def upload(self, storage_key: str, data: bytes, content_type: str) -> StoredFile:
        import io
        await self._run(
            self._client.upload_fileobj,
            io.BytesIO(data),
            self._bucket,
            storage_key,
            ExtraArgs={
                "ContentType": content_type,
                "ServerSideEncryption": "AES256",
            },
        )
        logger.debug("s3 upload key=%s size=%d", storage_key, len(data))
        return StoredFile(storage_key=storage_key, size=len(data), content_type=content_type)

    async def download(self, storage_key: str) -> bytes:
        import io

        buf = io.BytesIO()
        try:
            await self._run(self._client.download_fileobj, self._bucket, storage_key, buf)
        except Exception as exc:
            # botocore.exceptions.ClientError — translate to FileNotFoundError for callers
            if "NoSuchKey" in str(exc) or "404" in str(exc):
                raise FileNotFoundError(f"S3 object not found: {storage_key}") from exc
            raise
        return buf.getvalue()

    async def delete(self, storage_key: str) -> None:
        await self._run(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=storage_key,
        )
        logger.debug("s3 delete key=%s", storage_key)

    def get_url(self, storage_key: str) -> str | None:
        """Return a presigned URL valid for 1 hour."""
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": storage_key},
                ExpiresIn=_PRESIGNED_EXPIRY,
            )
        except Exception:
            logger.exception("Failed to generate presigned URL for key=%s", storage_key)
            return None
