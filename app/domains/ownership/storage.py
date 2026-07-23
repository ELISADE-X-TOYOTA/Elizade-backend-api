"""Document storage for ownership proof and warranty attachments."""

import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

_ALLOWED = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


@runtime_checkable
class StorageBackend(Protocol):
    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str: ...

    def delete(self, url: str) -> None: ...


class LocalStorage:
    def __init__(self, base_dir: str = "uploads/documents", base_url: str = "/media/documents") -> None:
        self.base_dir = Path(base_dir)
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _extension(filename: str | None, content_type: str | None) -> str:
        if filename and "." in filename:
            return filename.rsplit(".", 1)[1].lower()
        return _ALLOWED.get((content_type or "").lower(), "bin")

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


storage: StorageBackend = LocalStorage()
