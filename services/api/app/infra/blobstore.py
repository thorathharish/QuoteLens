"""Binary object storage for uploaded BOMs and exports: in-memory (tests/local) or GCS."""

import asyncio
from typing import Protocol

from app.domain.errors import NotFoundError


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes and return a URI for the object."""
        ...

    async def get(self, key: str) -> bytes: ...

    async def delete_prefix(self, prefix: str) -> None: ...


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self._objects[key] = bytes(data)
        return f"memory://{key}"

    async def get(self, key: str) -> bytes:
        try:
            return self._objects[key]
        except KeyError as exc:
            raise NotFoundError(f"Blob '{key}' not found") from exc

    async def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self._objects if k.startswith(prefix)]:
            del self._objects[key]


class GcsBlobStore:
    """Google Cloud Storage. The client is synchronous, so calls run in a worker thread."""

    def __init__(self, project: str | None, bucket: str) -> None:
        from google.cloud.storage import Client

        self._bucket = Client(project=project).bucket(bucket)
        self._bucket_name = bucket

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        blob = self._bucket.blob(key)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=content_type)
        return f"gs://{self._bucket_name}/{key}"

    async def get(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        try:
            data: bytes = await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)
        except NotFound as exc:
            raise NotFoundError(f"Blob '{key}' not found") from exc
        return data

    async def delete_prefix(self, prefix: str) -> None:
        def _delete() -> None:
            for blob in self._bucket.list_blobs(prefix=prefix):
                blob.delete()

        await asyncio.to_thread(_delete)
