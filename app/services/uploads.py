"""Folder-scoped upload handling.

Every customer upload used to funnel through `ownership_service.upload_document`
and land in one place, so a ticket screenshot, a trade-in photo and a VIN
document were indistinguishable once stored. Each source now has its own
storage instance and therefore its own folder in the bucket.

The validation is identical everywhere — same size cap, same content-type
allowlist — because the risk is identical: these files are served back from a
public origin, so a stored `.html` or `.svg` is script running from our own
domain. See `ownership/storage.py` for the extension rules.
"""

import logging

from fastapi import HTTPException, UploadFile, status

from app.domains.ownership.storage import UnsupportedFileType
from app.services import spaces
from app.services.spaces import build_storage

logger = logging.getLogger("elizade.uploads")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# One storage per source. `build_storage` returns a Spaces client when
# configured and a local-disk writer otherwise, so development needs no keys.
support_storage = build_storage(
    spaces.CUSTOMER_SUPPORT, local_dir="uploads/documents", local_url="/media/documents"
)
warranty_storage = build_storage(
    spaces.CUSTOMER_WARRANTY, local_dir="uploads/documents", local_url="/media/documents"
)
trade_in_storage = build_storage(
    spaces.CUSTOMER_TRADE_INS, local_dir="uploads/documents", local_url="/media/documents"
)
ownership_storage = build_storage(
    spaces.CUSTOMER_OWNERSHIP, local_dir="uploads/documents", local_url="/media/documents"
)
avatar_storage = build_storage(
    spaces.CUSTOMER_AVATARS, local_dir="uploads/documents", local_url="/media/documents"
)


def save_upload(file: UploadFile, storage) -> str:
    """Validate and store one upload, returning its URL.

    Raises 413 for oversize and 415 for a type we will not serve back.
    """
    from app.domains.shared.documents import validate_upload_content_type

    validate_upload_content_type(file.content_type)

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)",
        )

    try:
        return storage.save(
            content=content, filename=file.filename, content_type=file.content_type
        )
    except UnsupportedFileType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — object storage can be unavailable
        logger.exception("upload failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't store that file. Please try again.",
        ) from exc
