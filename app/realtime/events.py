"""The wire contract between the API and every realtime client.

Event names and payload shapes live here so the server, the mobile app and the
admin console are reading one definition rather than three that drift. Adding a
field is safe; renaming one is a breaking change to shipped clients that cannot
be forced to update.
"""

from __future__ import annotations

from typing import Any

# ── Server -> client ────────────────────────────────────────────────────
MESSAGE_RECEIVED = "ticket:message_received"
TYPING_START = "ticket:typing_start"
TYPING_STOP = "ticket:typing_stop"
STATUS_CHANGED = "ticket:status_changed"
READ_RECEIPT = "ticket:message_read"
#: Sent once on a successful join so the client knows the channel is live.
JOINED = "ticket:joined"
ERROR = "error"

# ── Client -> server ────────────────────────────────────────────────────
CLIENT_MESSAGE_SENT = "ticket:message_sent"
CLIENT_TYPING_START = "ticket:typing_start"
CLIENT_TYPING_STOP = "ticket:typing_stop"
CLIENT_MARK_READ = "ticket:mark_read"
CLIENT_PING = "ping"


def envelope(event: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every frame has the same two-key shape.

    A flat payload would force clients to guess whether a key is metadata or
    content, and makes adding transport-level fields later a breaking change.
    """
    return {"event": event, "data": data or {}}


def message_payload(message: Any, ticket_id: str) -> dict[str, Any]:
    """Full metadata for one message, per the realtime spec.

    Deliberately mirrors `TicketMessageOut` field-for-field: a client that can
    render a message from the REST list must be able to render one that
    arrived over the socket, without a second code path.
    """
    return {
        "ticketId": ticket_id,
        "id": message.id,
        "senderId": message.sender_id,
        "senderRole": message.sender_type.value
        if hasattr(message.sender_type, "value")
        else str(message.sender_type),
        "body": message.body,
        "attachments": list(message.attachments or []),
        "createdAt": message.created_at.isoformat() if message.created_at else None,
        "readAt": message.read_at.isoformat() if getattr(message, "read_at", None) else None,
    }
