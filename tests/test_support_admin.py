"""Support admin API tests."""

from datetime import datetime, timedelta, timezone

from app.domains.shared.enums import SlaStatus, TicketCategory, TicketPriority, TicketStatus
from app.domains.support.models import SlaConfig, SupportTicket


def _ticket(db, customer, *, number: str, subject: str, sla=SlaStatus.ok, status=TicketStatus.open):
    now = datetime.now(timezone.utc)
    row = SupportTicket(
        ticket_number=number,
        user_id=customer.id,
        category=TicketCategory.service,
        subject=subject,
        status=status,
        priority=TicketPriority.high,
        first_response_due=now + timedelta(hours=4),
        resolution_due=now + timedelta(days=2),
        sla_status=sla,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_support_requires_auth(client):
    assert client.get("/api/v1/admin/support/tickets").status_code == 401


def test_support_blocks_customer(client, customer_headers):
    assert client.get("/api/v1/admin/support/tickets", headers=customer_headers).status_code == 403


def test_support_summary(client, staff_headers, db_session, customer_user):
    _ticket(db_session, customer_user, number="TKT-T-010", subject="Summary test")
    res = client.get("/api/v1/admin/support/summary", headers=staff_headers)
    assert res.status_code == 200
    assert res.json()["openTickets"] >= 1


def test_list_tickets_and_sla(client, staff_headers, db_session, customer_user):
    _ticket(db_session, customer_user, number="TKT-T-001", subject="Brake issue")
    _ticket(
        db_session,
        customer_user,
        number="TKT-T-002",
        subject="SLA risk",
        sla=SlaStatus.at_risk,
    )
    db_session.add(
        SlaConfig(
            category=TicketCategory.service,
            response_hours=2,
            resolution_hours=24,
            is_active=True,
        )
    )
    db_session.commit()

    res = client.get("/api/v1/admin/support/tickets", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2

    sla = client.get("/api/v1/admin/support/sla-configs", headers=staff_headers)
    assert sla.status_code == 200
    assert len(sla.json()) >= 1


def test_create_ticket_and_update_sla(client, staff_headers, db_session, customer_user):
    sla_row = (
        db_session.query(SlaConfig)
        .filter(SlaConfig.category == TicketCategory.general)
        .one_or_none()
    )
    if not sla_row:
        sla_row = SlaConfig(
            category=TicketCategory.general,
            response_hours=12,
            resolution_hours=72,
            is_active=True,
        )
        db_session.add(sla_row)
        db_session.commit()
        db_session.refresh(sla_row)

    created = client.post(
        "/api/v1/admin/support/tickets",
        headers=staff_headers,
        json={
            "customerId": customer_user.id,
            "category": "general",
            "subject": "Admin-created ticket",
            "priority": "medium",
            "body": "Customer called in about billing.",
        },
    )
    assert created.status_code == 201
    assert created.json()["subject"] == "Admin-created ticket"
    assert len(created.json()["messages"]) == 1

    updated_sla = client.patch(
        f"/api/v1/admin/support/sla-configs/{sla_row.id}",
        headers=staff_headers,
        json={"responseHours": 6, "resolutionHours": 48},
    )
    assert updated_sla.status_code == 200
    assert updated_sla.json()["responseHours"] == 6


def test_reply_and_resolve_ticket(client, staff_headers, db_session, customer_user, staff_user):
    ticket = _ticket(db_session, customer_user, number="TKT-T-003", subject="Need help")

    reply = client.post(
        f"/api/v1/admin/support/tickets/{ticket.id}/messages",
        headers=staff_headers,
        json={"body": "We are looking into this for you."},
    )
    assert reply.status_code == 200
    assert reply.json()["message"]["body"] == "We are looking into this for you."

    detail = client.get(f"/api/v1/admin/support/tickets/{ticket.id}", headers=staff_headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 1

    resolved = client.post(f"/api/v1/admin/support/tickets/{ticket.id}/resolve", headers=staff_headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    assignees = client.get("/api/v1/admin/support/assignees", headers=staff_headers)
    assert assignees.status_code == 200
    assert any(a["id"] == staff_user.id for a in assignees.json())
