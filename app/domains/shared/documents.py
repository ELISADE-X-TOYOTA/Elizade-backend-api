"""Shared helpers for customer document and media uploads."""

import re

from fastapi import HTTPException, status

DOCUMENT_URL_PREFIX = "/media/documents/"
MAX_DOCUMENT_ATTACHMENTS = 5
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 120

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "application/pdf",
        "video/mp4",
        "video/quicktime",
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
            detail="Only JPEG, PNG, WebP, PDF, MP4, and MOV files are allowed",
        )


def _detected_type(content: bytes) -> str | None:
    """Return a conservative type based on magic bytes, never a client MIME."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    # MP4 and MOV both use an ISO BMFF `ftyp` box. Requiring a sane box
    # header prevents arbitrary files merely labelled as video being stored.
    if len(content) >= 12 and content[4:8] == b"ftyp":
        size = int.from_bytes(content[:4], "big")
        if 16 <= size <= len(content) and all(32 <= b < 127 for b in content[8:12]):
            return "video/quicktime" if content[8:12] in {b"qt  ", b"mqt "} else "video/mp4"
    return None


def _video_duration_seconds(content: bytes) -> float | None:
    """Read an ISO BMFF movie header when present.

    Fragmented recordings may not contain a usable `mvhd`; those are still
    accepted but remain bounded by the upload byte limit.
    """
    marker = b"mvhd"
    offset = content.find(marker)
    if offset < 4 or offset + 24 > len(content):
        return None
    version = content[offset + 4]
    if version == 0 and offset + 24 <= len(content):
        timescale = int.from_bytes(content[offset + 16 : offset + 20], "big")
        duration = int.from_bytes(content[offset + 20 : offset + 24], "big")
    elif version == 1 and offset + 36 <= len(content):
        timescale = int.from_bytes(content[offset + 28 : offset + 32], "big")
        duration = int.from_bytes(content[offset + 32 : offset + 36], "big")
    else:
        return None
    return duration / timescale if timescale else None


def validate_upload(content: bytes, filename: str | None, content_type: str | None) -> str:
    """Validate MIME, file signature, size, and video duration.

    Returns the canonical content type used by storage. Generic MIME headers
    are accepted only when the filename extension and bytes identify a type.
    """
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    declared = (content_type or "").lower().split(";", 1)[0].strip()
    suffix = filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""
    if declared and declared not in _ALLOWED_CONTENT_TYPES and declared != "application/octet-stream":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file type or file contents are not supported",
        )
    canonical = declared if declared in _ALLOWED_CONTENT_TYPES else next(
        (mime for mime, ext in _EXTENSIONS.items() if ext == suffix),
        None,
    )
    detected = _detected_type(content)
    if canonical is None or detected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file type or file contents are not supported",
        )
    # JPEG may be declared as image/jpg; otherwise the declared type must
    # agree with the signature. This blocks HTML/JS renamed as media.
    if canonical == "image/jpg":
        canonical = "image/jpeg"
    if detected != canonical:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file contents do not match the declared type",
        )

    max_bytes = MAX_VIDEO_BYTES if detected.startswith("video/") else MAX_DOCUMENT_BYTES
    if len(content) > max_bytes:
        limit = f"{max_bytes // (1024 * 1024)}MB"
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {limit})",
        )
    if detected.startswith("video/"):
        duration = _video_duration_seconds(content)
        if duration is not None and duration > MAX_VIDEO_DURATION_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Video too long (max {MAX_VIDEO_DURATION_SECONDS} seconds)",
            )
    return canonical


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
        key = url[len(DOCUMENT_URL_PREFIX) :] if url.startswith(DOCUMENT_URL_PREFIX) else ""
        if not _SAFE_KEY.fullmatch(key) or "/" in key or "\\" in key or ".." in key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment URL")
        if url not in out:
            out.append(url)
    return out
