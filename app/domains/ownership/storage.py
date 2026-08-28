"""Document storage for ownership proof and customer media attachments."""

import mimetypes
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

_ALLOWED = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
}

#: Extensions we will write, derived from the allowlist above.
#:
#: SECURITY: the extension decides how the static mount serves the file back.
#: `_extension` used to trust the uploaded filename, so `invoice.html` was
#: stored as `<uuid>.html` and served as text/html from our own origin — stored
#: XSS against anything sharing it (the admin panel). SVG is excluded for the
#: same reason: it is an image to users and a script host to browsers.
_ALLOWED_EXTENSIONS = set(_ALLOWED.values())


class UnsupportedFileType(ValueError):
    """Raised when an upload is not an allowed media type."""


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
        """Resolve a SAFE extension, or refuse the upload.

        Content type is trusted over the filename: a client that sends
        `image/png` gets `.png` regardless of what the file claims to be
        called. The filename is only consulted when the content type is
        missing or generic (`application/octet-stream`), and even then it must
        land in the allowlist.
        """
        declared = (content_type or "").lower().split(";")[0].strip()
        if declared in _ALLOWED:
            return _ALLOWED[declared]

        suffix = filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""
        if suffix in _ALLOWED_EXTENSIONS:
            return suffix

        raise UnsupportedFileType(
            f"Unsupported file type '{declared or suffix or 'unknown'}'. "
            "Allowed: JPEG, PNG, WebP, PDF, MP4, MOV."
        )

    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4().hex}.{self._extension(filename, content_type)}"
        (self.base_dir / key).write_bytes(content)
        return f"{self.base_url}/{key}"

    def path_for_key(self, key: str) -> Path | None:
        """Resolve a storage key without allowing path traversal."""
        if "/" in key or "\\" in key or key in (".", "..") or ".." in key:
            return None
        target = (self.base_dir / key).resolve()
        try:
            target.relative_to(self.base_dir.resolve())
        except ValueError:
            return None
        return target if target.is_file() else None

    @staticmethod
    def content_type_for_key(key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"

    def delete(self, url: str) -> None:
        key = url.rsplit("/", 1)[-1]
        target = self.path_for_key(key)
        if target is not None:
            target.unlink()


storage: StorageBackend = LocalStorage()
