"""
Image storage abstraction for inventory.

A thin interface so the upload/delete endpoints don't care where bytes live.
The default `LocalStorage` writes to disk and is enough for development; swap in
a Cloudinary/S3 backend later by replacing the module-level `storage` instance
(see `get_storage`). Tests monkeypatch `service.storage`, so no disk I/O runs
during the test suite.
"""

import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


@runtime_checkable
class StorageBackend(Protocol):
    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str:
        """Persist the bytes and return a retrievable URL."""

    def delete(self, url: str) -> None:
        """Best-effort removal of a previously saved object."""


class LocalStorage:
    """Stores files on the local filesystem under `base_dir`, served from `base_url`."""

    def __init__(self, base_dir: str = "uploads/vehicles", base_url: str = "/media/vehicles") -> None:
        self.base_dir = Path(base_dir)
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _extension(filename: str | None, content_type: str | None) -> str:
        if filename and "." in filename:
            return filename.rsplit(".", 1)[1].lower()
        return _EXTENSION_BY_CONTENT_TYPE.get((content_type or "").lower(), "bin")

    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4().hex}.{self._extension(filename, content_type)}"
        (self.base_dir / key).write_bytes(content)
        return f"{self.base_url}/{key}"

    def delete(self, url: str) -> None:
        key = url.rsplit("/", 1)[-1]
        target = self.base_dir / key
        if target.exists():
            target.unlink()


# Module-level instance used by the service layer. Replace this to change backends.
storage: StorageBackend = LocalStorage()
