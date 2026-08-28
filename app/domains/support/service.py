import math
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.domains.shared.enums import MessageSender, SlaStatus, TicketCategory, TicketPriority, TicketStatus
from app.domains.support.models import SlaConfig, SupportTicket, TicketMessage
from app.domains.support.schemas import (
    PaginatedTicketsOut,
    SlaConfigOut,
    SlaConfigUpdateIn,
    SupportSummaryOut,
    SupportTicketDetailOut,
    SupportTicketListItemOut,
    TicketCreateIn,
    TicketMessageCreateOut,
    TicketMessageOut,
    TicketUpdateIn,
)
from app.services import uploads
from app.services.uploads import save_upload
from app.domains.notifications import catalog
from app.domains.notifications.notify import safe_notify
from app.domains.support.customer_schemas import (
    AttachmentUploadOut,
    CustomerTicketCreateIn,
    CustomerTicketDetailOut,
    CustomerTicketListOut,
    CustomerTicketMessageCreateOut,
)
from app.domains.users.models import User, UserRole

OPEN_STATUSES = (
    TicketStatus.open,
    TicketStatus.assigned,
    TicketStatus.in_progress,
    TicketStatus.waiting_customer,
)

_ATTACHMENT_KEY = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|pdf|mp4|mov)$")


def get_summary(db: Session) -> SupportSummaryOut:
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_count = db.query(SupportTicket).filter(SupportTicket.status.in_(OPEN_STATUSES)).count()
    at_risk = db.query(SupportTicket).filter(SupportTicket.sla_status == SlaStatus.at_risk).count()
    unassigned = (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(OPEN_STATUSES), SupportTicket.assigned_to_id.is_(None))
        .count()
    )
    resolved_today = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.status.in_((TicketStatus.resolved, TicketStatus.closed)),
            SupportTicket.resolved_at.isnot(None),
            SupportTicket.resolved_at >= start_of_day,
        )
        .count()
    )
    return SupportSummaryOut(
        openTickets=open_count,
        atRiskTickets=at_risk,
        unassignedTickets=unassigned,
        resolvedToday=resolved_today,
    )


def list_assignees(db: Session) -> list[dict[str, str]]:
    rows = (
        db.query(User)
        .filter(User.role.in_((UserRole.staff, UserRole.admin)), User.is_active.is_(True))
        .order_by(User.first_name.asc())
        .all()
    )
    return [{"id": u.id, "name": f"{u.first_name} {u.last_name}".strip()} for u in rows]


def list_sla_configs(db: Session) -> list[SlaConfigOut]:
    rows = db.query(SlaConfig).order_by(SlaConfig.category.asc()).all()
    return [SlaConfigOut.from_model(r) for r in rows]


def update_sla_config(db: Session, config_id: str, payload: SlaConfigUpdateIn) -> SlaConfigOut:
    row = db.get(SlaConfig, config_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA config not found")

    if payload.response_hours is not None:
        row.response_hours = payload.response_hours
    if payload.resolution_hours is not None:
        row.resolution_hours = payload.resolution_hours
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.commit()
    db.refresh(row)
    return SlaConfigOut.from_model(row)


def _next_ticket_number(db: Session) -> str:
    count = db.query(func.count(SupportTicket.id)).scalar() or 0
    return f"TKT-{count + 1001:04d}"


def create_ticket(db: Session, payload: TicketCreateIn) -> SupportTicketDetailOut:
    customer = db.get(User, payload.customer_id)
    if not customer or customer.role != UserRole.customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer")

    try:
        category = TicketCategory(payload.category.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category") from exc

    try:
        priority = TicketPriority(payload.priority.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority") from exc

    sla = db.query(SlaConfig).filter(SlaConfig.category == category, SlaConfig.is_active.is_(True)).one_or_none()
    response_hours = sla.response_hours if sla else 8
    resolution_hours = sla.resolution_hours if sla else 72

    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        ticket_number=_next_ticket_number(db),
        user_id=customer.id,
        category=category,
        subject=payload.subject.strip(),
        status=TicketStatus.open,
        priority=priority,
        first_response_due=now + timedelta(hours=response_hours),
        resolution_due=now + timedelta(hours=resolution_hours),
        sla_status=SlaStatus.ok,
    )
    db.add(ticket)
    db.flush()

    if payload.body and payload.body.strip():
        db.add(
            TicketMessage(
                ticket_id=ticket.id,
                sender_type=MessageSender.staff,
                sender_id=None,
                body=payload.body.strip(),
            )
        )

    db.commit()
    return get_ticket(db, ticket.id)


def list_tickets(
    db: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    sla_status: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PaginatedTicketsOut:
    query = (
        db.query(SupportTicket)
        .options(
            joinedload(SupportTicket.customer),
            joinedload(SupportTicket.assigned_to),
        )
        .order_by(SupportTicket.updated_at.desc())
    )

    if status and status.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.status == TicketStatus(status.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter") from exc

    if category and category.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.category == TicketCategory(category.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category filter") from exc

    if sla_status and sla_status.strip().lower() != "all":
        try:
            query = query.filter(SupportTicket.sla_status == SlaStatus(sla_status.strip().lower()))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slaStatus filter") from exc

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.join(SupportTicket.customer).filter(
            (SupportTicket.subject.ilike(term))
            | (SupportTicket.ticket_number.ilike(term))
            | (User.first_name.ilike(term))
            | (User.last_name.ilike(term))
        )

    total = query.count()
    offset = (page - 1) * size
    rows = query.offset(offset).limit(size).all()
    pages = max(1, math.ceil(total / size)) if total else 1

    return PaginatedTicketsOut(
        items=[SupportTicketListItemOut.from_model(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def get_ticket(db: Session, ticket_id: str) -> SupportTicketDetailOut:
    ticket = (
        db.query(SupportTicket)
        .options(
            joinedload(SupportTicket.customer),
            joinedload(SupportTicket.assigned_to),
            joinedload(SupportTicket.messages).joinedload(TicketMessage.sender),
        )
        .filter(SupportTicket.id == ticket_id)
        .one_or_none()
    )
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return SupportTicketDetailOut.from_model(ticket)


def update_ticket(db: Session, ticket_id: str, payload: TicketUpdateIn) -> SupportTicketDetailOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Captured once, before anything below can change it. Assignment moves the
    # status too (open -> assigned), so comparing against the value on entry
    # announces that as well, not only a status the agent set explicitly.
    previous_status = ticket.status

    if payload.status is not None:
        try:
            new_status = TicketStatus(payload.status.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
        ticket.status = new_status
        if new_status in (TicketStatus.resolved, TicketStatus.closed) and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(timezone.utc)

    if payload.priority is not None:
        try:
            ticket.priority = TicketPriority(payload.priority.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority") from exc

    if payload.assigned_to_id is not None:
        if payload.assigned_to_id == "":
            ticket.assigned_to_id = None
        else:
            assignee = db.get(User, payload.assigned_to_id)
            if not assignee or assignee.role not in (UserRole.staff, UserRole.admin):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignee")
            ticket.assigned_to_id = assignee.id
            if ticket.status == TicketStatus.open:
                ticket.status = TicketStatus.assigned

    db.commit()
    db.refresh(ticket)

    if ticket.status != previous_status:
        _broadcast_status(ticket.id, ticket.status.value, previous_status.value)

    return get_ticket(db, ticket_id)


def add_staff_message(
    db: Session,
    ticket_id: str,
    *,
    staff_user: User,
    body: str,
    attachments: list[str] | None = None,
) -> TicketMessageCreateOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=MessageSender.staff,
        sender_id=staff_user.id,
        body=body.strip(),
        attachments=_validate_attachments(attachments or []),
    )
    db.add(message)

    if not ticket.first_response_at:
        ticket.first_response_at = now
    if ticket.status in (TicketStatus.open, TicketStatus.assigned):
        ticket.status = TicketStatus.in_progress

    db.commit()
    db.refresh(message)

    # Same reasoning as the notification below: after the commit, and unable
    # to fail the reply it announces.
    _broadcast_message(message, ticket.id)

    # After the commit: a notification is a side effect of a reply that has
    # already landed, and must not be able to roll it back.
    safe_notify(
        db,
        user=ticket.customer,
        event=catalog.TICKET_STAFF_REPLIED,
        context={
            "reference": ticket.ticket_number,
            "agent_name": f"{staff_user.first_name} {staff_user.last_name}".strip() or "Elizade Support",
            "subject": ticket.subject,
            "ticket_id": ticket.id,
        },
    )

    detail = get_ticket(db, ticket_id)
    latest = detail.messages[-1] if detail.messages else TicketMessageOut(
        id=message.id,
        senderType=MessageSender.staff.value,
        senderName=f"{staff_user.first_name} {staff_user.last_name}".strip(),
        body=message.body,
        createdAt=now.isoformat(),
    )
    return TicketMessageCreateOut(ticket=detail, message=latest)


def resolve_ticket(db: Session, ticket_id: str) -> SupportTicketDetailOut:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    ticket.status = TicketStatus.resolved
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()

    safe_notify(
        db,
        user=ticket.customer,
        event=catalog.TICKET_RESOLVED,
        context={
            "reference": ticket.ticket_number,
            "subject": ticket.subject,
            "ticket_id": ticket.id,
        },
    )
    return get_ticket(db, ticket_id)


def _get_customer_ticket(db: Session, user_id: str, ticket_id: str) -> SupportTicket:
    ticket = (
        db.query(SupportTicket)
        .options(
            joinedload(SupportTicket.customer),
            joinedload(SupportTicket.assigned_to),
            joinedload(SupportTicket.messages).joinedload(TicketMessage.sender),
        )
        .filter(SupportTicket.id == ticket_id, SupportTicket.user_id == user_id)
        .one_or_none()
    )
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


def create_customer_ticket(db: Session, user: User, payload: CustomerTicketCreateIn) -> CustomerTicketDetailOut:
    try:
        category = TicketCategory(payload.category.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category") from exc

    try:
        priority = TicketPriority(payload.priority.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid priority") from exc

    sla = db.query(SlaConfig).filter(SlaConfig.category == category, SlaConfig.is_active.is_(True)).one_or_none()
    response_hours = sla.response_hours if sla else 8
    resolution_hours = sla.resolution_hours if sla else 72

    now = datetime.now(timezone.utc)
    ticket = SupportTicket(
        ticket_number=_next_ticket_number(db),
        user_id=user.id,
        category=category,
        subject=payload.subject.strip(),
        status=TicketStatus.open,
        priority=priority,
        first_response_due=now + timedelta(hours=response_hours),
        resolution_due=now + timedelta(hours=resolution_hours),
        sla_status=SlaStatus.ok,
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_type=MessageSender.customer,
            sender_id=user.id,
            body=payload.body.strip(),
            # Evidence usually arrives WITH the report (a dashboard warning
            # light, a damaged part), so the opening message carries them too —
            # not only follow-up replies.
            attachments=_validate_attachments(payload.attachments or []),
        )
    )
    db.commit()

    safe_notify(
        db,
        user=user,
        event=catalog.TICKET_OPENED,
        context={
            "reference": ticket.ticket_number,
            "subject": ticket.subject,
            "sla_hours": response_hours,
            "ticket_id": ticket.id,
        },
    )
    return CustomerTicketDetailOut.from_model(_get_customer_ticket(db, user.id, ticket.id))


def list_customer_tickets(db: Session, user_id: str) -> list[CustomerTicketListOut]:
    rows = (
        db.query(SupportTicket)
        .options(joinedload(SupportTicket.customer), joinedload(SupportTicket.assigned_to))
        .filter(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.updated_at.desc())
        .limit(50)
        .all()
    )
    return [CustomerTicketListOut.from_model(r) for r in rows]


def get_customer_ticket(db: Session, user_id: str, ticket_id: str) -> CustomerTicketDetailOut:
    return CustomerTicketDetailOut.from_model(_get_customer_ticket(db, user_id, ticket_id))


#: Storage keys are `<uuid-hex>.<ext>` — nothing else is ours.
_ATTACHMENT_KEY = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,5}$")


def _attachment_url_prefixes() -> tuple[str, ...]:
    """Prefixes an attachment URL is allowed to start with.

    Read from the STORAGE BACKEND rather than hardcoded, because the two must
    agree and previously did not: this was pinned to the local-disk path
    `/media/documents/`, so the moment Spaces was configured every upload
    succeeded and was then rejected by the same API that had just issued the
    URL. Deriving it means the check cannot drift from the uploader again.

    Read lazily, not at import: `uploads` builds its storage instances at
    module load, and importing it from here at module scope is a cycle.
    """
    from app.services import uploads  # noqa: PLC0415

    prefixes = [uploads.support_storage.url_prefix]
    # Tickets opened before the move to Spaces still reference local-disk
    # URLs. Rejecting those would break replies on historical tickets.
    if "/media/" not in prefixes[0]:
        prefixes.append("/media/documents/")
    return tuple(prefixes)


#: Matches the ownership document cap — same store, same limit.
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def upload_attachment(file: UploadFile) -> AttachmentUploadOut:
    """Ticket attachments live under `customer/support/` in the bucket."""
    return AttachmentUploadOut(url=save_upload(file, uploads.support_storage))


logger = logging.getLogger("elizade.support")


def _validate_attachments(urls: list[str]) -> list[str]:
    """Accept only URLs this API issued, preserving order and dropping repeats.

    SECURITY: without this the field is an arbitrary-URL sink. A customer could
    reply with `https://attacker.example/pixel.png`, and the staff console would
    dutifully render it — leaking agent IPs and read receipts, or serving
    something worse. Requiring our own storage prefix and a safe single
    storage key means attachment references cannot escape the authenticated
    media endpoint.
    """
    cleaned: list[str] = []
    for raw in urls:
        url = (raw or "").strip()
        if not url:
            continue
        prefix = next((p for p in _attachment_url_prefixes() if url.startswith(p)), None)
        if prefix is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attachments must be uploaded via /support/attachments/upload",
            )
        key = url[len(prefix) :]
        if not _ATTACHMENT_KEY.match(key):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment reference")
    return cleaned


def add_customer_message(
    db: Session,
    user_id: str,
    ticket_id: str,
    body: str,
    attachments: list[str] | None = None,
) -> CustomerTicketMessageCreateOut:
    ticket = _get_customer_ticket(db, user_id, ticket_id)
    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticket is closed")

    files = _validate_attachments(attachments or [])
    text = body.strip()
    # A photo on its own is a complete reply; nothing at all is not.
    if not text and not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add a message or at least one attachment",
        )

    message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=MessageSender.customer,
        sender_id=user_id,
        body=text,
        attachments=files,
    )
    db.add(message)
    if ticket.status == TicketStatus.waiting_customer:
        ticket.status = TicketStatus.in_progress
    db.commit()
    db.refresh(message)
    detail = CustomerTicketDetailOut.from_model(_get_customer_ticket(db, user_id, ticket_id))
    # Serialise the row we actually created, rather than assuming it sorts last.
    # `created_at` defaults to `now()`, which in Postgres is TRANSACTION time —
    # so two messages written in one transaction carry identical timestamps and
    # `messages[-1]` can return the wrong one.
    latest = TicketMessageOut.from_model(message)

    # Also announce it to anyone holding a live socket on this ticket. The
    # REST and WebSocket paths must produce the SAME event, or an agent with
    # the console open sees replies only when the customer happens to have
    # used the socket path — which is invisible until it is reported as
    # "messages sometimes do not arrive".
    _broadcast_message(message, ticket.id)
    return CustomerTicketMessageCreateOut(ticket=detail, message=latest)


def rate_customer_ticket(db: Session, user_id: str, ticket_id: str, rating: int) -> CustomerTicketDetailOut:
    ticket = _get_customer_ticket(db, user_id, ticket_id)
    if ticket.status not in (TicketStatus.resolved, TicketStatus.closed):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket must be resolved before rating")
    ticket.satisfaction_rating = rating
    db.commit()
    return CustomerTicketDetailOut.from_model(_get_customer_ticket(db, user_id, ticket_id))


def list_customer_messages_since(
    db: Session,
    user_id: str,
    ticket_id: str,
    since: datetime | None = None,
) -> list[TicketMessageOut]:
    """Messages on a ticket, optionally only those after `since`.

    THE RECONNECT PATH. A dropped socket loses every frame sent while it was
    down, and the client cannot know what it missed — so on reconnect it asks
    for everything after the last message it holds. That is what makes the
    realtime layer safe to lose: the socket is an optimisation, and this is the
    guarantee underneath it.

    STRICTLY GREATER THAN, so the client's own last message is not returned to
    it again. Postgres `now()` is transaction time, so two messages written in
    one transaction share a timestamp — a `>=` here would re-deliver on every
    single reconnect.
    """
    ticket = _get_customer_ticket(db, user_id, ticket_id)

    query = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id)
    if since is not None:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        query = query.filter(TicketMessage.created_at > since)

    rows = query.order_by(TicketMessage.created_at.asc()).all()
    return [TicketMessageOut.from_model(r) for r in rows]


# ── Realtime fan-out ─────────────────────────────────────────────────────
#
# Imported lazily inside the helpers: `app.realtime` imports this module for
# `_validate_attachments`, so a module-scope import here is a cycle.
#
# None of these can fail the caller. A reply that saved but did not broadcast
# is a client that refetches a moment later; a broadcast that rolled back a
# saved reply would be a lost message.


def _broadcast_message(message: TicketMessage, ticket_id: str) -> None:
    try:
        from app.realtime import events
        from app.realtime.hub import broadcaster, ticket_room

        broadcaster.publish(
            ticket_room(ticket_id),
            events.envelope(events.MESSAGE_RECEIVED, events.message_payload(message, ticket_id)),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to broadcast message on ticket %s", ticket_id)


def _broadcast_status(ticket_id: str, new_status: str, previous_status: str) -> None:
    try:
        from app.realtime import events
        from app.realtime.hub import broadcaster, ticket_room

        broadcaster.publish(
            ticket_room(ticket_id),
            events.envelope(
                events.STATUS_CHANGED,
                {
                    "ticketId": ticket_id,
                    "status": new_status,
                    "previousStatus": previous_status,
                },
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to broadcast status on ticket %s", ticket_id)
