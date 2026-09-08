"""Shared helpers for customer document and media uploads."""

import re

from fastapi import HTTPException, status

#: The LOCAL-DISK prefix only. Kept because records written before the move to
#: object storage still reference it — it is a legacy fallback, NOT the answer
#: to "where do uploads live". Ask the storage backend that; see
#: `_document_url_prefixes`.
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

#: MUST cover every type in `_ALLOWED_CONTENT_TYPES`. The two lists had drifted:
#: video/mp4 and video/quicktime were accepted by `validate_upload_content_type`
#: and then had no extension to store under, so an mp4 walkaround video was
#: refused with "Allowed: JPEG, PNG, WebP, PDF" — an error that contradicted
#: the endpoint that had just accepted it. `app/services/spaces.py` already
#: mapped both; only this table was missing them.
_CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
}
_ALLOWED_EXTENSIONS = frozenset(_CONTENT_TYPE_TO_EXTENSION.values())

#: A FLAT storage filename — a stem with no dots or separators, then one safe
#: extension. Used with `fullmatch`, so nothing may precede or follow it, and
#: the charset admits no `/`, `\` or `.` in the stem. That is what stops
#: `../../etc/passwd` and every variation on it.
#:
#: WAS MISSING ENTIRELY. `normalize_document_urls` referenced this name without
#: it ever being defined, so every ownership claim submitted WITH documents
#: died on `NameError` — a 500 on the main path of the feature. It failed
#: closed, so nothing unsafe was accepted, but nothing valid was either.
#:
#: Deliberately NOT pinned to the `uuid4().hex` form that `LocalStorage.save`
#: currently emits. This validates a key the client hands back, and coupling it
#: to today's key-generation scheme would silently invalidate every stored file
#: the day that scheme changes. The shape is the security property; the exact
#: stem is not.
#:
#: The extension set is the one STORAGE can produce, deliberately wider than
#: this module's `_ALLOWED_EXTENSIONS`: support attachments include mp4/mov,
#: and rejecting a key here that the system itself wrote would be a second bug
#: wearing the first one's clothes.
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\.(?:jpg|jpeg|png|webp|pdf|mp4|mov)")


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
    # `_CONTENT_TYPE_TO_EXTENSION`, not `_EXTENSIONS` — the latter is a name
    # that has never existed in this module. A SECOND undefined reference
    # alongside `_SAFE_KEY`, and reachable on a real path: this branch runs
    # whenever the client sends `application/octet-stream` or no type at all,
    # which Android upload libraries routinely do. It raised NameError -> 500
    # rather than falling back to the filename extension as intended.
    canonical = declared if declared in _ALLOWED_CONTENT_TYPES else next(
        (mime for mime, ext in _CONTENT_TYPE_TO_EXTENSION.items() if ext == suffix),
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


def _document_url_prefixes() -> tuple[str, ...]:
    """Prefixes a stored-document URL is allowed to start with.

    READ FROM THE STORAGE BACKENDS, never hardcoded, because the uploader and
    the validator must agree and did not. `normalize_document_urls` was pinned
    to the local-disk path `/media/documents/`, which is correct only while
    storage IS local disk. Once Spaces credentials are configured — as they are
    in production — every upload endpoint starts issuing
    `https://<bucket>.<region>.digitaloceanspaces.com/<folder>/<key>`, and this
    function rejected every one of them. The file uploaded fine, then the
    submission carrying it died on "Invalid attachment URL": the API refusing a
    URL it had itself minted seconds earlier.

    That took out four customer features at once, in production only, while
    every local test passed — trade-in valuations, warranty claim evidence,
    service-appointment photos and VIN ownership documents. Support hit the
    identical bug earlier and was fixed by deriving its prefix this way; the
    other four kept the hardcoded copy. This is that fix, applied where it
    should have been applied in the first place.

    ALL CUSTOMER FOLDERS ARE ACCEPTED, not just the one matching the feature
    being submitted. The security property that matters is unchanged: the URL
    must be one this API issued into storage it controls, so the field cannot
    become a sink for `https://attacker.example/pixel.png`. Which FOLDER it
    landed in is an operational boundary — retention rules, bulk purges — and
    not an authorization one; every folder here holds uploads made by the same
    authenticated customer through an endpoint that already authorised them.
    Enforcing it here would only re-break the same class of bug the moment a
    client posts to a sibling upload endpoint, which is exactly what the app
    does today for trade-in photos.

    Read lazily, not at import: `uploads` builds its storage instances at
    module load and imports from this module, so a module-scope import is a
    cycle.
    """
    from app.services import uploads  # noqa: PLC0415

    prefixes: list[str] = []
    for storage in (
        uploads.trade_in_storage,
        uploads.warranty_storage,
        uploads.ownership_storage,
        uploads.support_storage,
        uploads.avatar_storage,
    ):
        prefix = getattr(storage, "url_prefix", "")
        if prefix and prefix not in prefixes:
            prefixes.append(prefix)
    # Rows created before the move to object storage still reference local-disk
    # URLs. Rejecting those would break editing or resubmitting historical
    # records for no gain.
    if DOCUMENT_URL_PREFIX not in prefixes:
        prefixes.append(DOCUMENT_URL_PREFIX)
    return tuple(prefixes)


def normalize_document_urls(urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    if len(urls) > MAX_DOCUMENT_ATTACHMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {MAX_DOCUMENT_ATTACHMENTS} attachments allowed",
        )
    prefixes = _document_url_prefixes()
    out: list[str] = []
    for raw in urls:
        url = (raw or "").strip()
        # A blank entry is a client artefact, not an attachment. Failing the
        # whole submission over one is punishing the customer for a trailing
        # empty slot in someone else's array.
        if not url:
            continue
        prefix = next((p for p in prefixes if url.startswith(p)), None)
        if prefix is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                # Names the cause. The old message said only "Invalid
                # attachment URL", which told a customer who had just filled in
                # a whole valuation form precisely nothing.
                detail="Attachments must be uploaded through this app before they can be submitted",
            )
        key = url[len(prefix) :]
        if not _SAFE_KEY.fullmatch(key) or "/" in key or "\\" in key or ".." in key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment URL")
        if url not in out:
            out.append(url)
    return out
