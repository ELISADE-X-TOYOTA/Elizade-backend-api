"""Local-disk storage, used whenever Spaces is not configured.

Keeps development zero-config: no credentials, no network, files under
`uploads/` served from the `/media` static mounts.

Extracted from the two per-domain copies that had drifted apart, so the
fallback behaves identically wherever it is used.
"""

import mimetypes
import uuid
from pathlib import Path

from app.domains.shared.documents import UnsupportedUploadExtension, upload_extension


class LocalStorage:
    def __init__(self, base_dir: str, base_url: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_url = base_url.rstrip("/")

    @property
    def url_prefix(self) -> str:
        return f"{self.base_url}/"

    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            ext = upload_extension(filename, content_type)
        except UnsupportedUploadExtension as exc:
            from app.domains.ownership.storage import UnsupportedFileType

            raise UnsupportedFileType(str(exc)) from exc
        key = f"{uuid.uuid4().hex}.{ext}"
        (self.base_dir / key).write_bytes(content)
        return f"{self.base_url}/{key}"

    def path_for_key(self, key: str) -> Path | None:
        """Resolve a storage key to a file on disk, or None.

        REQUIRED BY `main.serve_document`, which 404s when a backend does not
        provide it. This class did not, so in local-disk mode EVERY
        authenticated media fetch returned "Media not found" — ownership proof,
        support attachments, warranty evidence and avatars could all be
        uploaded and none could be read back.

        The working implementation lived on an orphaned second `LocalStorage`
        in `domains/ownership/storage.py` that `build_storage` never returns.
        Two classes of the same name, one of them dead: the extraction that
        created this module dropped the method, and nothing referenced the
        original again to notice.

        Traversal is refused rather than sanitised — a key is one flat
        filename, and anything else is a caller doing something it shouldn't.
        """
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
        """Also consulted by `serve_document`; without it everything is served
        as a download rather than rendered inline."""
        return mimetypes.guess_type(key)[0] or "application/octet-stream"

    def delete(self, url: str) -> None:
        key = url.rsplit("/", 1)[-1]
        target = self.base_dir / key
        # Guard against a stored URL escaping the directory it belongs to.
        if target.parent.resolve() != self.base_dir.resolve():
            return
        if target.exists():
            target.unlink()
