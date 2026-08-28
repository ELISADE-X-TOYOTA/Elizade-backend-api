"""The customer is told when an admin acts on their ownership claim.

None of this fired before. The catalogue defined `OWNERSHIP_CLAIM_APPROVED`
and `OWNERSHIP_CLAIM_REJECTED`, but nothing anywhere called them — so a claim
could be approved, declined, or parked pending documents and the customer was
never informed. They found out by opening the app and checking.

The document request is the case that matters most: it is the only one where
the claim STOPS until the customer acts. An unseen request is a claim stuck
in limbo, and the customer does not know it is their move.
"""

from app.domains.notifications.models import UserNotification
from app.domains.ownership.models import VehicleOwnershipRequest
from app.domains.ownership.service import DEFAULT_DOCUMENT_REQUEST
from app.domains.shared.enums import OwnershipRequestStatus

VIN = "JTMBBREV50D123456"


def _make_request(db_session, customer_user, **kwargs) -> VehicleOwnershipRequest:
    row = VehicleOwnershipRequest(
        user_id=customer_user.id,
        vin=kwargs.pop("vin", VIN),
        status=kwargs.pop("status", OwnershipRequestStatus.pending),
        document_urls=[],
        **kwargs,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _notifications(db_session, user_id) -> list[UserNotification]:
    return (
        db_session.query(UserNotification)
        .filter(UserNotification.user_id == user_id)
        .order_by(UserNotification.created_at.desc())
        .all()
    )


def _patch(client, admin_headers, request_id, body):
    return client.patch(
        f"/api/v1/admin/ownership/requests/{request_id}",
        json=body,
        headers=admin_headers,
    )


# ── Documents requested ──────────────────────────────────────────────────


def test_requesting_documents_notifies_the_customer(
    client, db_session, customer_user, admin_headers
):
    row = _make_request(db_session, customer_user)

    res = _patch(
        client,
        admin_headers,
        row.id,
        {"status": "pending_documents", "adminNotes": "a clearer photo of the vehicle licence"},
    )
    assert res.status_code == 200

    notes = _notifications(db_session, customer_user.id)
    assert len(notes) == 1, "the customer was not told their claim needs documents"
    assert "documents" in notes[0].title.lower()


def test_the_alert_says_which_documents(client, db_session, customer_user, admin_headers):
    """"We need something" is not actionable. The reviewer's note carries."""
    row = _make_request(db_session, customer_user)

    _patch(
        client,
        admin_headers,
        row.id,
        {"status": "pending_documents", "adminNotes": "a clearer photo of the vehicle licence"},
    )

    body = _notifications(db_session, customer_user.id)[0].body
    assert "a clearer photo of the vehicle licence" in body
    assert VIN in body, "the customer may have more than one claim open"


def test_missing_admin_notes_still_alerts(client, db_session, customer_user, admin_headers):
    """Vague beats silent — the customer still learns the ball is in their court."""
    row = _make_request(db_session, customer_user)

    _patch(client, admin_headers, row.id, {"status": "pending_documents"})

    notes = _notifications(db_session, customer_user.id)
    assert len(notes) == 1
    assert DEFAULT_DOCUMENT_REQUEST in notes[0].body


def test_blank_admin_notes_fall_back_too(client, db_session, customer_user, admin_headers):
    row = _make_request(db_session, customer_user)

    _patch(client, admin_headers, row.id, {"status": "pending_documents", "adminNotes": "   "})

    assert DEFAULT_DOCUMENT_REQUEST in _notifications(db_session, customer_user.id)[0].body


def test_the_alert_deep_links_somewhere_useful(
    client, db_session, customer_user, admin_headers
):
    row = _make_request(db_session, customer_user)
    _patch(client, admin_headers, row.id, {"status": "pending_documents"})

    # The stored column is "deep_link"; the mobile client maps it to a route.
    assert _notifications(db_session, customer_user.id)[0].deep_link


# ── The other decisions, also previously silent ──────────────────────────


def test_rejection_notifies_with_a_reason(client, db_session, customer_user, admin_headers):
    row = _make_request(db_session, customer_user)

    _patch(
        client,
        admin_headers,
        row.id,
        {"status": "rejected", "adminNotes": "chassis does not match our records"},
    )

    notes = _notifications(db_session, customer_user.id)
    assert len(notes) == 1
    assert "chassis does not match our records" in notes[0].body


def test_rejection_without_a_reason_still_notifies(
    client, db_session, customer_user, admin_headers
):
    row = _make_request(db_session, customer_user)
    _patch(client, admin_headers, row.id, {"status": "rejected"})

    assert len(_notifications(db_session, customer_user.id)) == 1


# ── Things that must NOT notify ──────────────────────────────────────────


def test_editing_notes_without_a_status_change_is_silent(
    client, db_session, customer_user, admin_headers
):
    """A reviewer typing notes is not an event the customer needs pushed."""
    row = _make_request(db_session, customer_user)

    _patch(client, admin_headers, row.id, {"adminNotes": "internal: chasing the branch"})

    assert _notifications(db_session, customer_user.id) == []


def test_setting_the_same_status_again_does_not_re_alert(
    client, db_session, customer_user, admin_headers
):
    """Re-saving a claim already pending documents must not spam the customer."""
    row = _make_request(db_session, customer_user, status=OwnershipRequestStatus.pending_documents)

    _patch(client, admin_headers, row.id, {"status": "pending_documents"})

    assert _notifications(db_session, customer_user.id) == [], "duplicate alert sent"


def test_a_second_distinct_request_does_alert_again(
    client, db_session, customer_user, admin_headers
):
    """Going back to pending and asking again IS a new request."""
    row = _make_request(db_session, customer_user, status=OwnershipRequestStatus.pending_documents)

    _patch(client, admin_headers, row.id, {"status": "pending"})
    _patch(client, admin_headers, row.id, {"status": "pending_documents", "adminNotes": "proof of address"})

    bodies = [n.body for n in _notifications(db_session, customer_user.id)]
    assert any("proof of address" in b for b in bodies)


# ── The claim decision outranks the alert ────────────────────────────────


def test_the_status_change_persists_even_if_notifying_fails(
    client, db_session, customer_user, admin_headers, monkeypatch
):
    """A notification is a side effect. The reviewer's decision must stand.

    `safe_notify` exists precisely so a failed alert cannot roll back the
    thing it was announcing.
    """
    import app.domains.ownership.service as ownership_service

    def _explode(*_args, **_kwargs):
        raise RuntimeError("push gateway down")

    monkeypatch.setattr(ownership_service, "safe_notify", _explode)

    row = _make_request(db_session, customer_user)
    res = _patch(client, admin_headers, row.id, {"status": "pending_documents"})

    assert res.status_code == 200
    db_session.refresh(row)
    assert row.status == OwnershipRequestStatus.pending_documents
