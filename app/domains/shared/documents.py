"""Shared helpers for customer document uploads (ownership, trade-in, warranty, support)."""

from fastapi import HTTPException, status

DOCUMENT_URL_PREFIX = "/media/documents/"
MAX_DOCUMENT_ATTACHMENTS = 5

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
)

_CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
_ALLOWED_EXTENSIONS = frozenset(_CONTENT_TYPE_TO_EXTENSION.values())


class UnsupportedUploadExtension(ValueError):
    """Raised when an upload's type cannot be mapped to a safe file extension."""


def validate_upload_content_type(content_type: str | None) -> None:
    if (content_type or "").lower().split(";")[0].strip() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only images and PDFs are allowed",
        )


def upload_extension(filename: str | None, content_type: str | None) -> str:
    """Resolve a safe extension, preferring the declared content type over the filename."""
    declared = (content_type or "").lower().split(";")[0].strip()
    if declared in _CONTENT_TYPE_TO_EXTENSION:
        return _CONTENT_TYPE_TO_EXTENSION[declared]

    suffix = filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""
    if suffix in _ALLOWED_EXTENSIONS:
        return suffix

    raise UnsupportedUploadExtension(
        f"Unsupported file type '{declared or suffix or 'unknown'}'. "
        "Allowed: JPEG, PNG, WebP, PDF."
    )


def normalize_document_urls(urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    if len(urls) > MAX_DOCUMENT_ATTACHMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {MAX_DOCUMENT_ATTACHMENTS} attachments allowed",
        )
    out: list[str] = []
    for raw in urls:
        url = raw.strip()
        if not url.startswith(DOCUMENT_URL_PREFIX):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment URL")
        if url not in out:
            out.append(url)
    return out
