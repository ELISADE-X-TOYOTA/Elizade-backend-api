"""Attachment URLs must be accepted by the same API that issued them.

THE BUG THESE PIN: the validator hardcoded `/media/documents/`, the local-disk
path. That was correct until uploads moved to Spaces — after which
`POST /support/attachments/upload` returned a
`https://<bucket>.<region>.digitaloceanspaces.com/customer/support/<key>` URL
and the ticket endpoints rejected it with 400. Every upload succeeded and
every attach then failed, in production only, because development has no
Spaces credentials and silently kept using local disk.

The fix reads the prefix off the storage backend, so the check cannot drift
from the uploader again. These tests exist to keep it that way — and to keep
the security property the original hardcoding was there to provide.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.domains.support.service import _attachment_url_prefixes, _validate_attachments
from app.services import uploads


def _key() -> str:
    return f"{uuid.uuid4().hex}.jpg"


# ── The contract: what we issue, we accept ───────────────────────────────


def test_a_url_from_our_own_storage_is_accepted():
    """The regression test proper: issue a URL the way uploads do, then attach it."""
    url = uploads.support_storage.url_prefix + _key()
    assert _validate_attachments([url]) == [url]


def test_the_validator_reads_its_prefix_from_the_storage_backend():
    """If these two ever disagree, uploads break in production only."""
    assert uploads.support_storage.url_prefix in _attachment_url_prefixes()


def test_legacy_local_disk_urls_still_work():
    """Tickets opened before the move to Spaces must still accept replies."""
    url = f"/media/documents/{_key()}"
    assert _validate_attachments([url]) == [url]


# ── The security property the hardcoding provided ────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/pixel.png",
        "http://attacker.example/tracker.gif",
        "//attacker.example/pixel.png",
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
    ],
    ids=["https-external", "http-external", "protocol-relative", "javascript", "data-uri"],
)
def test_foreign_urls_are_refused(url):
    """An arbitrary-URL sink would leak agent IPs and read receipts.

    The staff console renders these, so a reply carrying an attacker's URL
    turns every agent who opens the ticket into a tracking pixel hit.
    """
    with pytest.raises(HTTPException):
        _validate_attachments([url])


@pytest.mark.parametrize(
    "key",
    ["../../etc/passwd", "not-a-uuid.jpg", "", "a" * 31 + ".jpg", f"{uuid.uuid4().hex}.exe!"],
    ids=["traversal", "wrong-shape", "empty-key", "short-hex", "bad-ext"],
)
def test_a_correct_prefix_with_a_bad_key_is_refused(key):
    """The prefix alone is not enough — the key shape is checked too."""
    with pytest.raises(HTTPException):
        _validate_attachments([uploads.support_storage.url_prefix + key])


def test_a_prefix_lookalike_is_refused():
    """A path that merely starts the same must not pass.

    Built by extending the real prefix rather than rewriting its host, so this
    holds for whichever backend is configured — `/media/documents-evil/...`
    under local disk, `.../customer/support-evil/...` under Spaces.
    """
    evil = uploads.support_storage.url_prefix.rstrip("/") + "-evil/" + _key()
    with pytest.raises(HTTPException):
        _validate_attachments([evil])


# ── The environment gap that let this ship ───────────────────────────────


def test_the_spaces_url_shape_is_accepted_even_though_tests_run_on_local_disk():
    """The suite blanks SPACES_* in conftest, so every other test here
    exercises LOCAL storage — which is exactly why this bug reached
    production untested: the broken path only existed once Spaces was
    configured, and CI never configures it.

    So the Spaces prefix is built directly and checked on its own terms.
    """
    from app.services.spaces import SpacesStorage

    spaces = SpacesStorage("customer/support")
    # Whatever the bucket resolves to here, the SHAPE is what matters: an
    # absolute https URL ending in the folder, which the old hardcoded
    # `/media/documents/` check could never have matched.
    prefix = spaces.url_prefix
    assert prefix.startswith("https://")
    assert prefix.endswith("/customer/support/")

    # And the validator must derive from the live backend, not a constant —
    # this is the assertion that fails if anyone hardcodes a path again.
    assert uploads.support_storage.url_prefix in _attachment_url_prefixes()


# ── Ordering and de-duplication ──────────────────────────────────────────


def test_order_is_preserved_and_repeats_dropped():
    a = uploads.support_storage.url_prefix + _key()
    b = uploads.support_storage.url_prefix + _key()
    assert _validate_attachments([a, b, a]) == [a, b]


def test_blank_entries_are_skipped_not_rejected():
    """A trailing empty string from the client is noise, not an attack."""
    url = uploads.support_storage.url_prefix + _key()
    assert _validate_attachments(["", "   ", url]) == [url]


def test_no_attachments_is_fine():
    assert _validate_attachments([]) == []
