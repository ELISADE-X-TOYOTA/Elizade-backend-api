"""The ticket WebSocket gateway.

    wss://<host>/api/v1/ws/tickets/{ticket_id}?token=<access token>

ONE SOCKET PER TICKET, not one per user. A ticket thread is the unit of
authorisation — a customer may read their own tickets and nobody else's — so
binding the socket to a ticket lets that check happen ONCE, at handshake, and
never again per frame. A single multiplexed socket would have to re-authorise
every inbound message against a room name the client supplied, which is the
shape of bug that leaks other people's conversations.

Every inbound message is PERSISTED BEFORE IT IS BROADCAST. A message that was
shown to both parties but never written is worse than one that is briefly slow:
the customer believes support has it, and support has nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.shared.enums import MessageSender
from app.domains.support import service as support_service
from app.domains.support.models import SupportTicket, TicketMessage
from app.domains.users.models import User, UserRole
from app.realtime import events
from app.realtime.auth import authenticate
from app.realtime.hub import Connection, hub, ticket_room

logger = logging.getLogger("elizade.realtime")

router = APIRouter(tags=["realtime"])

#: RFC 6455 close codes.
_CLOSE_POLICY = 1008  # policy violation — auth failed or access denied
_CLOSE_NOT_FOUND = 1011

#: A body longer than this is refused rather than truncated: silently storing
#: half of what someone typed is worse than telling them it was too long.
MAX_WS_BODY = 5000


def _may_access(db: Session, user: User, ticket_id: str) -> SupportTicket | None:
    """The single authorisation gate for this socket.

    Staff may open any ticket. A customer may open only their own — checked by
    owner id, not by anything the client sends.
    """
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        return None

    if user.role in (UserRole.admin, UserRole.staff):
        return ticket
    if ticket.customer_id == user.id:
        return ticket
    return None


@router.websocket("/ws/tickets/{ticket_id}")
async def ticket_socket(
    websocket: WebSocket,
    ticket_id: str,
    db: Session = Depends(get_db),
) -> None:
    """
    The session comes through `Depends(get_db)` rather than being opened here.
    Two reasons, and the second is the one that bit:

      * it is the same session lifecycle as every other endpoint, so an
        override applies to sockets too — without it the socket reads a
        different connection than the rest of the request path and cannot see
        data written in an open transaction;
      * a SQLAlchemy Session releases its pool connection on commit, so an
        idle socket between frames holds nothing. Holding the session for the
        socket's lifetime therefore does not pin a database connection per
        open chat.
    """
    connection: Connection | None = None

    try:
        user = authenticate(websocket, db)
        if user is None:
            # Refused BEFORE accept: the handshake fails outright, so an
            # unauthenticated peer never gets an open channel to send on.
            await websocket.close(code=_CLOSE_POLICY)
            return

        ticket = _may_access(db, user, ticket_id)
        if ticket is None:
            await websocket.close(code=_CLOSE_POLICY)
            return

        await websocket.accept()

        role = "staff" if user.role in (UserRole.admin, UserRole.staff) else "customer"
        connection = Connection(socket=websocket, user_id=user.id, role=role)
        room = ticket_room(ticket_id)
        await hub.join(connection, room)

        await websocket.send_json(
            events.envelope(
                events.JOINED,
                {"ticketId": ticket_id, "role": role, "status": ticket.status.value},
            )
        )

        while True:
            frame = await websocket.receive_json()
            await _handle(db, websocket, connection, ticket_id, frame, user, role)

    except WebSocketDisconnect:
        pass  # the ordinary way a socket ends
    except Exception:  # noqa: BLE001
        logger.exception("ticket socket failed for %s", ticket_id)
        try:
            await websocket.close(code=_CLOSE_NOT_FOUND)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if connection is not None:
            await hub.disconnect(connection)
        # `db` is closed by the dependency, not here.


async def _handle(
    db: Session,
    websocket: WebSocket,
    connection: Connection,
    ticket_id: str,
    frame: dict,
    user: User,
    role: str,
) -> None:
    """Dispatch one inbound frame."""
    event = frame.get("event")
    data = frame.get("data") or {}
    room = ticket_room(ticket_id)

    if event == events.CLIENT_PING:
        await websocket.send_json(events.envelope("pong"))
        return

    # ── typing ──────────────────────────────────────────────────────────
    # Not persisted, and excluded from the sender. Typing state is worthless
    # a second later, so writing it down would be pure cost.
    if event in (events.CLIENT_TYPING_START, events.CLIENT_TYPING_STOP):
        outbound = (
            events.TYPING_START if event == events.CLIENT_TYPING_START else events.TYPING_STOP
        )
        await hub.broadcast(
            room,
            events.envelope(outbound, {"ticketId": ticket_id, "userId": user.id, "role": role}),
            exclude=connection,
        )
        return

    # ── read receipts ───────────────────────────────────────────────────
    if event == events.CLIENT_MARK_READ:
        marked = _mark_read(db, ticket_id, user, role)
        if marked:
            await hub.broadcast(
                room,
                events.envelope(
                    events.READ_RECEIPT,
                    {"ticketId": ticket_id, "messageIds": marked, "readerRole": role},
                ),
            )
        return

    # ── a new message ───────────────────────────────────────────────────
    if event == events.CLIENT_MESSAGE_SENT:
        await _handle_message(db, websocket, ticket_id, data, user, role, room)
        return

    await websocket.send_json(
        events.envelope(events.ERROR, {"detail": f"Unknown event: {event}"})
    )


async def _handle_message(
    db: Session,
    websocket: WebSocket,
    ticket_id: str,
    data: dict,
    user: User,
    role: str,
    room: str,
) -> None:
    body = str(data.get("body") or "").strip()
    attachments = data.get("attachments") or []
    #: Echoed back on the ack so the client can match this to its optimistic
    #: bubble; without it a slow network shows the message twice.
    client_ref = data.get("clientRef")

    if len(body) > MAX_WS_BODY:
        await websocket.send_json(
            events.envelope(events.ERROR, {"detail": "Message is too long", "clientRef": client_ref})
        )
        return

    if not body and not attachments:
        await websocket.send_json(
            events.envelope(
                events.ERROR,
                {"detail": "Add a message or at least one attachment", "clientRef": client_ref},
            )
        )
        return

    try:
        # Reuses the REST validator, so an attachment URL is checked by exactly
        # the same rule on both paths. A socket must not be a way around it.
        files = support_service._validate_attachments(list(attachments))
    except Exception as exc:  # noqa: BLE001 — HTTPException carries the reason
        detail = getattr(exc, "detail", "That attachment could not be accepted")
        await websocket.send_json(
            events.envelope(events.ERROR, {"detail": str(detail), "clientRef": client_ref})
        )
        return

    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        await websocket.send_json(events.envelope(events.ERROR, {"detail": "Ticket not found"}))
        return

    from app.domains.shared.enums import TicketStatus

    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        await websocket.send_json(
            events.envelope(
                events.ERROR, {"detail": "Ticket is closed", "clientRef": client_ref}
            )
        )
        return

    # PERSIST FIRST. Everything below this line assumes the row exists.
    message = TicketMessage(
        ticket_id=ticket_id,
        sender_type=MessageSender.staff if role == "staff" else MessageSender.customer,
        sender_id=user.id,
        body=body,
        attachments=files,
    )
    db.add(message)

    previous_status = ticket.status
    if role == "customer" and ticket.status == TicketStatus.waiting_customer:
        ticket.status = TicketStatus.in_progress
    elif role == "staff" and ticket.status == TicketStatus.open:
        ticket.status = TicketStatus.in_progress

    db.commit()
    db.refresh(message)

    payload = events.message_payload(message, ticket_id)
    payload["clientRef"] = client_ref
    await hub.broadcast(room, events.envelope(events.MESSAGE_RECEIVED, payload))

    if ticket.status != previous_status:
        await hub.broadcast(
            room,
            events.envelope(
                events.STATUS_CHANGED,
                {
                    "ticketId": ticket_id,
                    "status": ticket.status.value,
                    "previousStatus": previous_status.value,
                },
            ),
        )


def _mark_read(db: Session, ticket_id: str, user: User, role: str) -> list[str]:
    """Stamp the OTHER side's unread messages as read. Returns their ids.

    Only the counterpart's messages are marked: stamping your own would report
    that you had read what you wrote, which tells the other party nothing.
    """
    counterpart = MessageSender.customer if role == "staff" else MessageSender.staff

    rows = (
        db.query(TicketMessage)
        .filter(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.sender_type == counterpart,
            TicketMessage.read_at.is_(None),
        )
        .all()
    )
    if not rows:
        return []

    now = datetime.now(timezone.utc)
    for row in rows:
        row.read_at = now
    db.commit()
    return [r.id for r in rows]
