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


def validate_upload_content_type(content_type: str | None) -> None:
    if (content_type or "").lower() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only images and PDFs are allowed",
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
