"""Dashboard summary API tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.shared.enums import (
    AvailabilityStatus,
    BroadcastCampaignStatus,
    ClaimStatus,
    NotificationCategory,
    SlaStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.domains.support.models import SupportTicket
from app.domains.users.models import UserRole
from app.domains.warranty.models import WarrantyClaim


def test_dashboard_summary_requires_auth(client):
    res = client.get("/api/v1/admin/dashboard/summary")
    assert res.status_code == 401


def test_dashboard_summary_customer_forbidden(client, customer_headers):
    res = client.get("/api/v1/admin/dashboard/summary", headers=customer_headers)
    assert res.status_code == 403


def test_dashboard_summary_empty_counts(client, staff_headers):
    res = client.get("/api/v1/admin/dashboard/summary", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["vehiclesTotal"] == 0
    assert data["customersTotal"] == 0
    assert data["openSupportTickets"] == 0
    assert data["pendingWarrantyClaims"] == 0
    assert data["activeNotificationRules"] == 0


def test_dashboard_summary_reflects_seeded_data(
    client,
    staff_headers,
    db_session,
    branch,
    vehicle_factory,
    customer_user,
    admin_user,
):
    vehicle_factory(availability=AvailabilityStatus.available)
    vehicle_factory(availability=AvailabilityStatus.reserved)
    vehicle_factory(availability=AvailabilityStatus.sold, is_published=False)

    now = datetime.now(timezone.utc)
    db_session.add(
        SupportTicket(
            ticket_number="TKT-001",
            user_id=customer_user.id,
            category=TicketCategory.service,
            subject="Brake noise",
            status=TicketStatus.open,
            priority=TicketPriority.medium,
            first_response_due=now + timedelta(hours=4),
            resolution_due=now + timedelta(days=2),
            sla_status=SlaStatus.at_risk,
        )
    )
    db_session.add(
        SupportTicket(
            ticket_number="TKT-002",
            user_id=customer_user.id,
            category=TicketCategory.general,
            subject="Resolved issue",
            status=TicketStatus.resolved,
            priority=TicketPriority.low,
            first_response_due=now - timedelta(hours=1),
            resolution_due=now + timedelta(days=1),
            sla_status=SlaStatus.ok,
        )
    )

    owned = OwnedVehicle(
        user_id=customer_user.id,
        vin="1HGBH41JXMN109186",
        make="Toyota",
        model="Camry",
        trim="XLE",
        year=2022,
        color="Silver",
        registration_number="LAG-123-XY",
        mileage=12000,
    )
    db_session.add(owned)
    db_session.flush()

    db_session.add(
        WarrantyClaim(
            user_id=customer_user.id,
            owned_vehicle_id=owned.id,
            claim_type="Engine",
            description="Unusual vibration under load",
            status=ClaimStatus.under_review,
        )
    )
    db_session.add(
        NotificationRule(
            name="Service reminder",
            trigger_key="service_due_soon",
            channels=["in_app"],
            cadence="daily",
            is_active=True,
        )
    )
    db_session.add(
        NotificationRule(
            name="Disabled rule",
            trigger_key="marketing_opt_in",
            channels=["in_app"],
            cadence="weekly",
            is_active=False,
        )
    )
    db_session.add(
        BroadcastCampaign(
            title="Sent campaign",
            body="Hello",
            segment_key="all_customers",
            channels=["in_app"],
            status=BroadcastCampaignStatus.sent,
            reach_count=1,
            sent_at=now,
        )
    )
    db_session.add(
        UserNotification(
            user_id=customer_user.id,
            title="Welcome",
            body="Thanks for joining Elizade Connect",
            category=NotificationCategory.system,
            is_read=False,
        )
    )
    db_session.commit()

    res = client.get("/api/v1/admin/dashboard/summary", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["vehiclesTotal"] == 3
    assert data["vehiclesAvailable"] == 1
    assert data["vehiclesReserved"] == 1
    assert data["customersTotal"] >= 1
    assert data["staffTotal"] >= 2
    assert data["openSupportTickets"] == 1
    assert data["slaAtRiskTickets"] == 1
    assert data["pendingWarrantyClaims"] == 1
    assert data["activeNotificationRules"] == 1
    assert data["campaignsSent"] == 1
    assert data["unreadNotificationsTotal"] == 1
