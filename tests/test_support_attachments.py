"""Attachments on customer ticket replies.

Covers the upload endpoint's content-type gate, the reply payload's URL
validation, and persistence through to the ticket detail response.

The URL-validation cases carry the most weight: `attachments` is a
client-supplied list of strings, so without a whitelist it is an arbitrary-URL
sink rendered by the staff console.
"""

import io

import pytest

from app.core.security import create_access_token
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole

SUPPORT = "/api/v1/support/tickets"
UPLOAD = "/api/v1/support/attachments/upload"

# Smallest valid PNG (1x1, transparent).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db4" "0000000049454e44ae426082"
)


@pytest.fixture
def other_customer_headers(db_session) -> dict[str, str]:
    user = User(
        phone_normalized="8100000011",
        phone_display="08100000011",
        first_name="Chidi",
        last_name="Eze",
        email="attach.other@elizade.test",
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=dict(DEFAULT_PREFERENCES),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _open_ticket(client, headers) -> str:
    res = client.post(
        SUPPORT,
        headers=headers,
        json={
            "category": "service",
            "subject": "Dashboard warning light",
            "body": "A warning light came on this morning.",
            "priority": "medium",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _upload(client, headers, *, name="photo.png", data=PNG_BYTES, ctype="image/png"):
    return client.post(UPLOAD, headers=headers, files={"file": (name, io.BytesIO(data), ctype)})


# ── Upload endpoint ──────────────────────────────────────────────────────


def test_upload_returns_a_media_url(client, customer_headers):
    res = _upload(client, customer_headers)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert url.startswith("/media/documents/")
    assert url.endswith(".png")


def test_upload_requires_authentication(client):
    assert _upload(client, {}).status_code == 401


def test_upload_rejects_staff(client, staff_headers):
    assert _upload(client, staff_headers).status_code == 403


def test_upload_rejects_empty_file(client, customer_headers):
    assert _upload(client, customer_headers, data=b"").status_code == 400


@pytest.mark.parametrize(
    "name,ctype",
    [
        ("payload.html", "text/html"),
        ("payload.svg", "image/svg+xml"),
        ("payload.exe", "application/x-msdownload"),
        ("payload.js", "text/javascript"),
    ],
)
def test_upload_rejects_script_capable_types(client, customer_headers, name, ctype):
    """A stored .html or .svg would be served as script from our own origin."""
    res = _upload(client, customer_headers, name=name, data=b"<script>alert(1)</script>", ctype=ctype)
    assert res.status_code == 415


def test_upload_ignores_a_lying_filename(client, customer_headers):
    """Content type wins: a real PNG called `evil.html` is stored as .png."""
    res = _upload(client, customer_headers, name="evil.html", ctype="image/png")
    assert res.status_code == 200
    assert res.json()["url"].endswith(".png")


# ── Replies carrying attachments ─────────────────────────────────────────


def test_reply_persists_attachments_onto_the_thread(client, customer_headers):
    ticket_id = _open_ticket(client, customer_headers)
    url = _upload(client, customer_headers).json()["url"]

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "Here is the warning light.", "attachments": [url]},
    )
    assert res.status_code == 200, res.text
    message_id = res.json()["message"]["id"]
    assert res.json()["message"]["attachments"] == [url]

    # And it survives a re-read of the ticket. Located by id rather than by
    # position: `created_at` defaults to transaction time, so messages written
    # inside one transaction (as they are under the test fixture) tie, and
    # thread position is not a safe way to identify a specific message.
    detail = client.get(f"{SUPPORT}/{ticket_id}", headers=customer_headers).json()
    stored = next(m for m in detail["messages"] if m["id"] == message_id)
    assert stored["attachments"] == [url]
    assert stored["body"] == "Here is the warning light."


def test_attachment_only_reply_is_allowed(client, customer_headers):
    """A photo with no words is a complete reply."""
    ticket_id = _open_ticket(client, customer_headers)
    url = _upload(client, customer_headers).json()["url"]

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "", "attachments": [url]},
    )
    assert res.status_code == 200
    assert res.json()["message"]["attachments"] == [url]


def test_reply_with_neither_body_nor_attachment_is_rejected(client, customer_headers):
    ticket_id = _open_ticket(client, customer_headers)
    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "   ", "attachments": []},
    )
    assert res.status_code == 400


def test_existing_replies_still_work_without_the_field(client, customer_headers):
    """The field is optional — older clients must keep working unchanged."""
    ticket_id = _open_ticket(client, customer_headers)
    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "No attachment here."},
    )
    assert res.status_code == 200
    assert res.json()["message"]["attachments"] == []


def test_duplicate_attachment_urls_are_collapsed(client, customer_headers):
    ticket_id = _open_ticket(client, customer_headers)
    url = _upload(client, customer_headers).json()["url"]

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "Same file twice.", "attachments": [url, url]},
    )
    assert res.status_code == 200
    assert res.json()["message"]["attachments"] == [url]


# ── URL validation: the field must not accept arbitrary URLs ─────────────


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://attacker.example/pixel.png",       # external tracking pixel
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "/media/documents/../../etc/passwd",        # traversal
        "/media/vehicles/some-car.jpg",             # our host, wrong bucket
        "javascript:alert(1)",
        "/media/documents/not-a-uuid.png",          # right prefix, wrong key shape
    ],
)
def test_reply_rejects_urls_we_did_not_issue(client, customer_headers, bad_url):
    ticket_id = _open_ticket(client, customer_headers)
    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "See attached.", "attachments": [bad_url]},
    )
    assert res.status_code == 400, f"{bad_url} was accepted"


def test_reply_rejects_more_than_five_attachments(client, customer_headers):
    ticket_id = _open_ticket(client, customer_headers)
    urls = [_upload(client, customer_headers).json()["url"] for _ in range(6)]

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=customer_headers,
        json={"body": "Too many.", "attachments": urls},
    )
    assert res.status_code == 422


def test_non_owner_still_cannot_attach_to_someone_elses_ticket(
    client, customer_headers, other_customer_headers
):
    ticket_id = _open_ticket(client, customer_headers)
    url = _upload(client, other_customer_headers).json()["url"]

    res = client.post(
        f"{SUPPORT}/{ticket_id}/messages",
        headers=other_customer_headers,
        json={"body": "Not my ticket.", "attachments": [url]},
    )
    assert res.status_code == 404


# ── Attachments on the opening message ───────────────────────────────────


def test_new_ticket_can_carry_attachments(client, customer_headers):
    url = _upload(client, customer_headers).json()["url"]
    res = client.post(
        SUPPORT,
        headers=customer_headers,
        json={
            "category": "service",
            "subject": "Cracked windscreen",
            "body": "Photo of the crack attached.",
            "priority": "medium",
            "attachments": [url],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["messages"][0]["attachments"] == [url]


def test_new_ticket_rejects_foreign_attachment_urls(client, customer_headers):
    res = client.post(
        SUPPORT,
        headers=customer_headers,
        json={
            "category": "service",
            "subject": "Cracked windscreen",
            "body": "See attached.",
            "priority": "medium",
            "attachments": ["https://attacker.example/pixel.png"],
        },
    )
    assert res.status_code == 400
