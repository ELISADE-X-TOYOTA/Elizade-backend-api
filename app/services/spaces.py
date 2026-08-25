"""DigitalOcean Spaces object storage, with one folder per upload source.

Every upload is namespaced by WHO produced it and WHAT it is:

    admin/vehicles/<uuid>.jpg          inventory photography
    customer/support/<uuid>.jpg        ticket attachments
    customer/warranty/<uuid>.jpg       claim evidence
    customer/trade-ins/<uuid>.jpg      trade-in photos
    customer/ownership/<uuid>.pdf      VIN claim documents
    customer/avatars/<uuid>.jpg        profile photos

The admin/customer split is the top level on purpose. It is the boundary that
matters operationally: customer uploads are user-generated content subject to
retention and deletion requests, admin uploads are catalogue assets that get
published. Keeping them apart means a lifecycle rule, a bulk purge or a
permission change can target one without touching the other — which is
impossible once everything shares a flat namespace.

ADDRESSING: virtual-hosted (`<bucket>.<region>.digitaloceanspaces.com`), which
is Spaces' native form. Path-style against the bare regional host is not
reliably resolvable.
"""

import logging
import uuid
from typing import Protocol, runtime_checkable

from app.core.config import get_settings

logger = logging.getLogger("elizade.spaces")

#: Upload folders. Add here rather than passing raw strings around, so the
#: bucket layout is described in one place.
ADMIN_VEHICLES = "admin/vehicles"
CUSTOMER_SUPPORT = "customer/support"
CUSTOMER_WARRANTY = "customer/warranty"
CUSTOMER_TRADE_INS = "customer/trade-ins"
CUSTOMER_OWNERSHIP = "customer/ownership"
CUSTOMER_AVATARS = "customer/avatars"

ALL_FOLDERS = (
    ADMIN_VEHICLES,
    CUSTOMER_SUPPORT,
    CUSTOMER_WARRANTY,
    CUSTOMER_TRADE_INS,
    CUSTOMER_OWNERSHIP,
    CUSTOMER_AVATARS,
)


@runtime_checkable
class StorageBackend(Protocol):
    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str: ...

    def delete(self, url: str) -> None: ...


class SpacesStorage:
    """One instance per folder. `save` returns a public CDN URL."""

    def __init__(self, folder: str) -> None:
        settings = get_settings()
        self.folder = folder.strip("/")
        self.bucket = settings.spaces_bucket
        self.region = settings.spaces_region
        self._client = None  # built lazily so importing this module never does I/O

    @property
    def client(self):
        if self._client is None:
            import boto3  # noqa: PLC0415 — keep boto3 off the import path when unused
            from botocore.client import Config

            settings = get_settings()
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.spaces_endpoint,
                aws_access_key_id=settings.spaces_key,
                aws_secret_access_key=settings.spaces_secret,
                region_name=settings.spaces_region,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "virtual"},
                    retries={"max_attempts": 3},
                ),
            )
        return self._client

    def public_url(self, key: str) -> str:
        return f"https://{self.bucket}.{self.region}.digitaloceanspaces.com/{key}"

    def save(self, *, content: bytes, filename: str | None, content_type: str | None) -> str:
        from app.domains.shared.documents import UnsupportedUploadExtension, upload_extension

        try:
            ext = upload_extension(filename, content_type)
        except UnsupportedUploadExtension as exc:
            from app.domains.ownership.storage import UnsupportedFileType

            raise UnsupportedFileType(str(exc)) from exc

        key = f"{self.folder}/{uuid.uuid4().hex}.{ext}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
            # Media is referenced directly by the app and admin portal, so it
            # has to be readable without a signed URL.
            ACL="public-read",
            # Content-addressed keys never change, so they can be cached hard.
            CacheControl="public, max-age=31536000, immutable",
        )
        logger.info("[SPACES] stored %s (%s bytes)", key, len(content))
        return self.public_url(key)

    def delete(self, url: str) -> None:
        key = self._key_from_url(url)
        if not key:
            return
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info("[SPACES] deleted %s", key)
        except Exception:  # noqa: BLE001 — deletion is best effort
            logger.warning("[SPACES] could not delete %s", key, exc_info=True)

    def _key_from_url(self, url: str) -> str | None:
        """Recover the object key, refusing anything outside this folder.

        A delete driven by a stored URL must not be able to reach into another
        folder — a malformed or tampered record should be a no-op, not a
        cross-folder deletion.
        """
        marker = f"/{self.folder}/"
        if marker not in url:
            return None
        return url.split("/", 3)[-1] if url.startswith("http") else url.lstrip("/")


def build_storage(folder: str, *, local_dir: str, local_url: str) -> StorageBackend:
    """Spaces when configured, local disk otherwise.

    Development stays zero-config: without Spaces credentials the app writes to
    `uploads/` and serves from `/media/` exactly as before.
    """
    settings = get_settings()
    if settings.spaces_configured:
        logger.info("[SPACES] %s -> %s/%s", folder, settings.spaces_bucket, folder)
        return SpacesStorage(folder)

    from app.services.local_storage import LocalStorage  # noqa: PLC0415

    logger.info("[SPACES] not configured — %s stays on local disk", folder)
    return LocalStorage(base_dir=local_dir, base_url=local_url)
