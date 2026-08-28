"""Local-disk storage, used whenever Spaces is not configured.

Keeps development zero-config: no credentials, no network, files under
`uploads/` served from the `/media` static mounts.

Extracted from the two per-domain copies that had drifted apart, so the
fallback behaves identically wherever it is used.
"""

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

    def delete(self, url: str) -> None:
        key = url.rsplit("/", 1)[-1]
        target = self.base_dir / key
        # Guard against a stored URL escaping the directory it belongs to.
        if target.parent.resolve() != self.base_dir.resolve():
            return
        if target.exists():
            target.unlink()
