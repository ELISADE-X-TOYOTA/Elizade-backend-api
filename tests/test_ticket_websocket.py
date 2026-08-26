"""The ticket WebSocket gateway, driven through a real client.

`TestClient.websocket_connect` runs the actual endpoint — handshake, auth,
room join, frame dispatch — so these cover the contract a shipped mobile app
depends on rather than the internals of the hub (see `test_realtime_hub.py`
for those).

The load-bearing tests here are the authorisation ones. A socket that opens on
someone else's ticket streams a stranger's support conversation, and unlike a
REST leak it keeps streaming.
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.domains.shared.enums import MessageSender, TicketCategory, TicketStatus
from app.domains.support.models import SupportTicket, TicketMessage
from app.realtime import events

WS = "/api/v1/ws/tickets"


def _ticket(db_session, customer_user, **kwargs) -> SupportTicket:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        ticket_number=kwargs.pop("number", "TKT-9001"),
        user_id=customer_user.id,
        category=TicketCategory.general,
        subject="Warning light on dashboard",
        status=kwargs.pop("status", TicketStatus.open),
        first_response_due=now + timedelta(hours=8),
        resolution_due=now + timedelta(hours=72),
        **kwargs,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def _url(ticket_id: str, user) -> str:
    return f"{WS}/{ticket_id}?token={create_access_token(user.id)}"


# ── Handshake and authorisation ──────────────────────────────────────────


def test_a_valid_token_opens_the_socket(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        frame = ws.receive_json()
    assert frame["event"] == events.JOINED
    assert frame["data"]["ticketId"] == ticket.id
    assert frame["data"]["role"] == "customer"


def test_no_token_is_refused(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{WS}/{ticket.id}") as ws:
            ws.receive_json()


def test_a_garbage_token_is_refused(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{WS}/{ticket.id}?token=not-a-jwt") as ws:
            ws.receive_json()


def test_a_customer_cannot_open_someone_elses_ticket(
    client, db_session, customer_user, admin_user
):
    """The one that matters: an open socket keeps streaming, unlike a REST leak."""
    ticket = _ticket(db_session, customer_user)

    # A second customer, who has nothing to do with this ticket.
    from app.domains.users.models import User, UserRole

    other = User(
        email="intruder@example.com",
        phone="+2348030000999",
        first_name="Not",
        last_name="Yours",
        role=UserRole.customer,
        is_active=True,
        is_verified=True,
    )
    db_session.add(other)
    db_session.commit()

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_url(ticket.id, other)) as ws:
            ws.receive_json()


def test_staff_may_open_any_ticket(client, db_session, customer_user, staff_user):
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, staff_user)) as ws:
        frame = ws.receive_json()
    assert frame["data"]["role"] == "staff"


def test_an_unknown_ticket_is_refused(client, customer_user):
    import uuid

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_url(str(uuid.uuid4()), customer_user)) as ws:
            ws.receive_json()


# ── Messages ─────────────────────────────────────────────────────────────


def test_a_message_is_persisted_before_it_is_broadcast(client, db_session, customer_user):
    """The spec's ordering, and the one that protects against a lost message."""
    ticket = _ticket(db_session, customer_user)

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()  # joined
        ws.send_json(
            {"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "The light is still on"}}
        )
        frame = ws.receive_json()

    assert frame["event"] == events.MESSAGE_RECEIVED
    # By the time the broadcast arrives the row must already exist.
    row = (
        db_session.query(TicketMessage)
        .filter(TicketMessage.ticket_id == ticket.id)
        .one()
    )
    assert row.body == "The light is still on"
    assert frame["data"]["id"] == row.id


def test_the_payload_carries_the_metadata_clients_need(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "hello"}})
        data = ws.receive_json()["data"]

    for key in ("id", "ticketId", "senderId", "senderRole", "body", "attachments", "createdAt"):
        assert key in data, f"payload is missing {key}"
    assert data["senderRole"] == MessageSender.customer.value
    assert data["senderId"] == customer_user.id


def test_the_client_ref_comes_back_so_optimistic_bubbles_can_be_matched(
    client, db_session, customer_user
):
    """Without this a slow network shows the message twice."""
    ticket = _ticket(db_session, customer_user)

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json(
            {"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "hi", "clientRef": "draft-7"}}
        )
        assert ws.receive_json()["data"]["clientRef"] == "draft-7"


def test_an_empty_message_is_refused(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "   "}})
        assert ws.receive_json()["event"] == events.ERROR


def test_an_overlong_message_is_refused_not_truncated(client, db_session, customer_user):
    """Silently storing half of what someone typed is worse than refusing it."""
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "x" * 6000}})
        assert ws.receive_json()["event"] == events.ERROR
    assert db_session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count() == 0


def test_a_foreign_attachment_url_is_refused_over_the_socket_too(
    client, db_session, customer_user
):
    """The socket must not be a way around the REST attachment validator."""
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json(
            {
                "event": events.CLIENT_MESSAGE_SENT,
                "data": {"body": "see this", "attachments": ["https://attacker.example/x.png"]},
            }
        )
        assert ws.receive_json()["event"] == events.ERROR


def test_a_closed_ticket_refuses_new_messages(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user, status=TicketStatus.closed, number="TKT-9002")
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "hello?"}})
        assert ws.receive_json()["event"] == events.ERROR


# ── Typing, status, receipts ─────────────────────────────────────────────


def test_an_unknown_event_is_reported_not_ignored(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": "ticket:teleport", "data": {}})
        assert ws.receive_json()["event"] == events.ERROR


def test_ping_gets_a_pong(client, db_session, customer_user):
    """The client's liveness check — a socket can be open and yet dead."""
    ticket = _ticket(db_session, customer_user)
    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_PING})
        assert ws.receive_json()["event"] == "pong"


def test_marking_read_stamps_the_other_sides_messages(client, db_session, customer_user):
    ticket = _ticket(db_session, customer_user)
    staff_msg = TicketMessage(
        ticket_id=ticket.id, sender_type=MessageSender.staff, body="We are looking into it"
    )
    db_session.add(staff_msg)
    db_session.commit()

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MARK_READ})
        frame = ws.receive_json()

    assert frame["event"] == events.READ_RECEIPT
    db_session.refresh(staff_msg)
    assert staff_msg.read_at is not None


def test_marking_read_does_not_stamp_your_own_messages(client, db_session, customer_user):
    """Reporting that you read what you wrote tells the other party nothing."""
    ticket = _ticket(db_session, customer_user)
    mine = TicketMessage(
        ticket_id=ticket.id,
        sender_type=MessageSender.customer,
        sender_id=customer_user.id,
        body="my own message",
    )
    db_session.add(mine)
    db_session.commit()

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MARK_READ})
        ws.send_json({"event": events.CLIENT_PING})
        # No receipt should precede the pong.
        assert ws.receive_json()["event"] == "pong"

    db_session.refresh(mine)
    assert mine.read_at is None


def test_a_customer_reply_moves_waiting_customer_to_in_progress(
    client, db_session, customer_user
):
    ticket = _ticket(
        db_session, customer_user, status=TicketStatus.waiting_customer, number="TKT-9003"
    )

    with client.websocket_connect(_url(ticket.id, customer_user)) as ws:
        ws.receive_json()
        ws.send_json({"event": events.CLIENT_MESSAGE_SENT, "data": {"body": "here you go"}})
        first = ws.receive_json()
        second = ws.receive_json()

    assert first["event"] == events.MESSAGE_RECEIVED
    assert second["event"] == events.STATUS_CHANGED
    assert second["data"]["status"] == TicketStatus.in_progress.value
    assert second["data"]["previousStatus"] == TicketStatus.waiting_customer.value
