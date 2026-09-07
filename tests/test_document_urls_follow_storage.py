"""The API rejecting URLs it had just issued itself.

`normalize_document_urls` hardcoded the LOCAL-DISK prefix `/media/documents/`.
That is correct only while storage is local disk. Production has Spaces
credentials, so every upload endpoint returns

    https://<bucket>.<region>.digitaloceanspaces.com/<folder>/<key>

and this function rejected all of them. The upload succeeded, the customer saw
their photo attached, and the submission carrying it died with 400 "Invalid
attachment URL" — the API refusing a URL it minted seconds earlier.

Four customer features, production only, every local test green: trade-in
valuations, warranty claim evidence, service-appointment photos, and VIN
ownership documents. The reported symptom was "unable to submit car for
evaluation".

Local disk is why it hid. These tests therefore run the validator against BOTH
backends, because a test suite that only ever sees local disk is exactly what
let this ship.
"""

import pytest
from fastapi import HTTPException

from app.domains.shared import documents
from app.services import uploads

SALES = "/api/v1/sales"

BUCKET = "https://elizade-test.fra1.digitaloceanspaces.com"
KEY = "a3f1c09b74e5426d81b0f2c7d95e4a18.jpg"


class _FakeSpaces:
    """Mirrors `SpacesStorage.url_prefix` — folder included, trailing slash."""

    def __init__(self, folder: str) -> None:
        self.folder = folder

    @property
    def url_prefix(self) -> str:
        return f"{BUCKET}/{self.folder}/"


@pytest.fixture
def on_spaces(monkeypatch):
    """Put every customer store on object storage, as production is."""
    folders = {
        "trade_in_storage": "customer/trade-ins",
        "warranty_storage": "customer/warranty",
        "ownership_storage": "customer/ownership",
        "support_storage": "customer/support",
        "avatar_storage": "customer/avatars",
    }
    for attr, folder in folders.items():
        monkeypatch.setattr(uploads, attr, _FakeSpaces(folder))
    return folders


def _url(folder: str, key: str = KEY) -> str:
    return f"{BUCKET}/{folder}/{key}"


# ── The bug ──────────────────────────────────────────────────────────────


def test_a_url_the_upload_endpoint_issued_is_accepted(on_spaces):
    """THE CORE OF IT. Whatever the uploader returns, the validator must take."""
    issued = uploads.trade_in_storage.url_prefix + KEY

    assert documents.normalize_document_urls([issued]) == [issued], (
        "the API rejected an attachment URL it had just issued"
    )


@pytest.mark.parametrize(
    "folder",
    ["customer/trade-ins", "customer/warranty", "customer/ownership", "customer/support"],
)
def test_every_customer_upload_folder_is_accepted(on_spaces, folder):
    """The four features that broke together, plus the one already fixed.

    Folder is not an authorization boundary: the app uploads trade-in photos
    through the support endpoint today, so scoping this per-feature would leave
    the reported bug in place while looking like a fix.
    """
    url = _url(folder)
    assert documents.normalize_document_urls([url]) == [url]


def test_local_disk_urls_still_work(monkeypatch):
    """Development, and every row written before the move to Spaces."""
    local = documents.DOCUMENT_URL_PREFIX + KEY
    assert documents.normalize_document_urls([local]) == [local]


def test_local_urls_survive_the_switch_to_spaces(on_spaces):
    """Historical records must not become unsubmittable on deploy day."""
    local = documents.DOCUMENT_URL_PREFIX + KEY
    assert documents.normalize_document_urls([local]) == [local]


# ── Still a security boundary ────────────────────────────────────────────


def test_an_arbitrary_url_is_still_refused(on_spaces):
    """The field must not become a sink for someone else's host.

    A staff console renders these; an attacker-controlled URL there leaks agent
    IPs and read receipts at best.
    """
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls(["https://attacker.example/pixel.png"])
    assert exc.value.status_code == 400


def test_a_lookalike_bucket_is_refused(on_spaces):
    """Prefix matching must not be fooled by a similar hostname."""
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls(
            [f"https://elizade-test.fra1.digitaloceanspaces.com.evil.test/customer/support/{KEY}"]
        )
    assert exc.value.status_code == 400


def test_traversal_out_of_the_folder_is_refused(on_spaces):
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls([_url("customer/support", "../../etc/passwd")])
    assert exc.value.status_code == 400


def test_a_nested_key_is_refused(on_spaces):
    """A key is one segment. Slashes would let a URL address another folder."""
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls([_url("customer/support", "nested/other.jpg")])
    assert exc.value.status_code == 400


def test_an_executable_extension_is_refused(on_spaces):
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls([_url("customer/support", "payload.svg")])
    assert exc.value.status_code == 400


def test_the_refusal_message_says_what_to_do(on_spaces):
    """A customer who has filled in a whole form deserves better than
    "Invalid attachment URL"."""
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls(["https://attacker.example/pixel.png"])
    assert "upload" in exc.value.detail.lower(), exc.value.detail


# ── Housekeeping ─────────────────────────────────────────────────────────


def test_the_cap_still_applies(on_spaces):
    too_many = [_url("customer/trade-ins", f"{i:032x}.jpg") for i in range(6)]
    with pytest.raises(HTTPException) as exc:
        documents.normalize_document_urls(too_many)
    assert exc.value.status_code == 400
    assert "5" in exc.value.detail


def test_duplicates_collapse_and_order_holds(on_spaces):
    a = _url("customer/trade-ins", f"{1:032x}.jpg")
    b = _url("customer/trade-ins", f"{2:032x}.jpg")
    assert documents.normalize_document_urls([a, b, a]) == [a, b]


def test_a_blank_entry_does_not_fail_the_submission(on_spaces):
    """An empty slot in a client's array is not a reason to lose the form."""
    url = _url("customer/trade-ins")
    assert documents.normalize_document_urls(["", url, "   "]) == [url]


def test_no_attachments_is_fine(on_spaces):
    assert documents.normalize_document_urls([]) == []
    assert documents.normalize_document_urls(None) == []


# ── End to end, through the endpoint the tester used ─────────────────────


def test_submitting_a_trade_in_with_photos_on_spaces(client, customer_headers, on_spaces):
    """The exact reported journey: complete the evaluation form, submit.

    The existing trade-in test passes no photos, which is why local disk never
    caught this.
    """
    resp = client.post(
        f"{SALES}/trade-ins",
        headers=customer_headers,
        json={
            "make": "Toyota",
            "model": "Camry",
            "year": 2018,
            "mileage": 85000,
            "conditionNotes": "Good condition — regularly serviced, minor cosmetic wear.",
            "photoUrls": [_url("customer/trade-ins"), _url("customer/support")],
        },
    )

    assert resp.status_code == 201, resp.text
    assert len(resp.json()["photoUrls"]) == 2, "the photos were dropped"


def test_submitting_a_trade_in_with_a_foreign_url_is_refused(
    client, customer_headers, on_spaces
):
    resp = client.post(
        f"{SALES}/trade-ins",
        headers=customer_headers,
        json={
            "make": "Toyota",
            "model": "Camry",
            "year": 2018,
            "mileage": 85000,
            "conditionNotes": "Good condition — regularly serviced, minor cosmetic wear.",
            "photoUrls": ["https://attacker.example/pixel.png"],
        },
    )
    assert resp.status_code == 400
