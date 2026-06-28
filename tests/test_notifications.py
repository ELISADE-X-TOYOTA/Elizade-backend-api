"""Notification engine and customer feed tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token
from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.shared.enums import BroadcastCampaignStatus, NotificationCategory
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole
from app.services.email import clear_sent_messages, get_sent_messages
from app.services.push import clear_sent_pushes, get_sent_pushes


@pytest.fixture(autouse=True)
def _clear_delivery_logs():
    clear_sent_messages()
    clear_sent_pushes()
    yield
    clear_sent_messages()
    clear_sent_pushes()


def _owned_vehicle(db_session, user: User, *, days_until_service: int) -> OwnedVehicle:
    row = OwnedVehicle(
        user_id=user.id,
        vin=f"VIN{user.phone_normalized[-6:]}",
        make="Toyota",
        model="Corolla",
        trim="LE",
        year=2023,
        color="White",
        registration_number=f"REG-{user.phone_normalized[-4:]}",
        mileage=8000,
        next_service_due=datetime.now(timezone.utc) + timedelta(days=days_until_service),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _customer_with_prefs(db_session, phone: str, email: str, *, marketing_opt_in: bool, email_enabled: bool = True, push_enabled: bool = True) -> User:
    prefs = dict(DEFAULT_PREFERENCES)
    prefs["marketing_opt_in"] = marketing_opt_in
    prefs["email_enabled"] = email_enabled
    prefs["push_enabled"] = push_enabled
    user = User(
        phone_normalized=phone,
        phone_display=f"0{phone}",
        first_name="Test",
        last_name="User",
        email=email,
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        preferences=prefs,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# Admin auth boundaries                                                       #
# --------------------------------------------------------------------------- #


def test_notifications_admin_requires_auth(client):
    assert client.get("/api/v1/admin/notifications/rules").status_code == 401
    assert client.get("/api/v1/admin/notifications/campaigns").status_code == 401


def test_notifications_admin_blocks_customers(client, customer_headers):
    assert client.get("/api/v1/admin/notifications/rules", headers=customer_headers).status_code == 403


def test_staff_can_list_rules_and_campaigns(client, staff_headers, db_session, admin_headers):
    db_session.add(
        NotificationRule(
            name="Rule A",
            trigger_key="service_due_soon",
            channels=["in_app"],
            cadence="daily",
            is_active=True,
        )
    )
    db_session.commit()

    rules = client.get("/api/v1/admin/notifications/rules", headers=staff_headers)
    assert rules.status_code == 200
    assert len(rules.json()) == 1

    campaigns = client.get("/api/v1/admin/notifications/campaigns", headers=staff_headers)
    assert campaigns.status_code == 200


# --------------------------------------------------------------------------- #
# Rule CRUD + validation                                                      #
# --------------------------------------------------------------------------- #


def test_create_rule_validates_trigger_and_channels(client, admin_headers):
    bad_trigger = client.post(
        "/api/v1/admin/notifications/rules",
        headers=admin_headers,
        json={
            "name": "Bad",
            "triggerKey": "unknown_trigger",
            "channels": ["in_app"],
        },
    )
    assert bad_trigger.status_code == 400

    bad_channels = client.post(
        "/api/v1/admin/notifications/rules",
        headers=admin_headers,
        json={
            "name": "Bad channels",
            "triggerKey": "service_due_soon",
            "channels": ["sms"],
        },
    )
    assert bad_channels.status_code == 400

    ok = client.post(
        "/api/v1/admin/notifications/rules",
        headers=admin_headers,
        json={
            "name": "Service reminder",
            "triggerKey": "service_due_soon",
            "channels": ["in_app", "email", "push"],
            "cadence": "daily",
            "isActive": True,
            "config": {"days_before": 7},
        },
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["name"] == "Service reminder"
    assert body["triggerKey"] == "service_due_soon"
    assert set(body["channels"]) == {"in_app", "email", "push"}


def test_update_rule_and_toggle_active(client, admin_headers, db_session):
    rule = NotificationRule(
        name="Original",
        trigger_key="marketing_opt_in",
        channels=["in_app"],
        cadence="weekly",
        is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    res = client.patch(
        f"/api/v1/admin/notifications/rules/{rule.id}",
        headers=admin_headers,
        json={"name": "Updated name", "isActive": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Updated name"
    assert data["isActive"] is False


def test_only_admin_can_create_rules(client, staff_headers):
    res = client.post(
        "/api/v1/admin/notifications/rules",
        headers=staff_headers,
        json={
            "name": "Staff attempt",
            "triggerKey": "service_due_soon",
            "channels": ["in_app"],
        },
    )
    assert res.status_code == 403


# --------------------------------------------------------------------------- #
# Rule evaluation — service_due_soon                                          #
# --------------------------------------------------------------------------- #


def test_evaluate_service_due_soon_matches_and_dispatches(client, admin_headers, db_session):
    due_soon = _customer_with_prefs(db_session, "8100000101", "due@elizade.test", marketing_opt_in=False)
    not_due = _customer_with_prefs(db_session, "8100000102", "ok@elizade.test", marketing_opt_in=False)
    _owned_vehicle(db_session, due_soon, days_until_service=5)
    _owned_vehicle(db_session, not_due, days_until_service=30)

    rule = NotificationRule(
        name="Due soon",
        trigger_key="service_due_soon",
        channels=["in_app", "email", "push"],
        cadence="daily",
        is_active=True,
        config={"days_before": 14},
    )
    db_session.add(rule)
    db_session.commit()

    res = client.post(f"/api/v1/admin/notifications/rules/{rule.id}/evaluate", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["matchedUsers"] == 1
    assert data["notificationsCreated"] == 1
    assert data["emailsSent"] == 1
    assert data["pushesSent"] == 1

    emails = get_sent_messages()
    assert len(emails) == 1
    assert emails[0]["to_email"] == "due@elizade.test"
    assert emails[0]["category"] == "service"

    pushes = get_sent_pushes()
    assert len(pushes) == 1
    assert pushes[0]["user_id"] == due_soon.id

    feed = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {create_access_token(due_soon.id)}"},
    )
    assert feed.status_code == 200
    assert len(feed.json()) == 1
    assert feed.json()[0]["category"] == "service"


def test_evaluate_inactive_rule_rejected(client, admin_headers, db_session):
    rule = NotificationRule(
        name="Off",
        trigger_key="service_due_soon",
        channels=["in_app"],
        cadence="daily",
        is_active=False,
    )
    db_session.add(rule)
    db_session.commit()

    res = client.post(f"/api/v1/admin/notifications/rules/{rule.id}/evaluate", headers=admin_headers)
    assert res.status_code == 400


def test_evaluate_respects_user_preferences(client, admin_headers, db_session):
    user = _customer_with_prefs(
        db_session,
        "8100000103",
        "nopush@elizade.test",
        marketing_opt_in=False,
        email_enabled=False,
        push_enabled=False,
    )
    _owned_vehicle(db_session, user, days_until_service=3)

    rule = NotificationRule(
        name="Due soon",
        trigger_key="service_due_soon",
        channels=["in_app", "email", "push"],
        cadence="daily",
        is_active=True,
        config={"days_before": 14},
    )
    db_session.add(rule)
    db_session.commit()

    res = client.post(f"/api/v1/admin/notifications/rules/{rule.id}/evaluate", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["notificationsCreated"] == 1
    assert data["emailsSent"] == 0
    assert data["pushesSent"] == 0
    assert get_sent_messages() == []
    assert get_sent_pushes() == []


# --------------------------------------------------------------------------- #
# Rule evaluation — marketing_opt_in                                          #
# --------------------------------------------------------------------------- #


def test_evaluate_marketing_rule_only_opted_in_and_respects_promo_prefs(client, admin_headers, db_session):
    opted_in = _customer_with_prefs(db_session, "8100000201", "optin@elizade.test", marketing_opt_in=True)
    opted_out = _customer_with_prefs(db_session, "8100000202", "optout@elizade.test", marketing_opt_in=False)
    no_email = _customer_with_prefs(
        db_session,
        "8100000203",
        "noemail@elizade.test",
        marketing_opt_in=True,
        email_enabled=False,
    )

    rule = NotificationRule(
        name="Promo blast",
        trigger_key="marketing_opt_in",
        channels=["in_app", "email"],
        cadence="weekly",
        is_active=True,
        config={"title": "Summer sale", "body": "Save on service packages"},
    )
    db_session.add(rule)
    db_session.commit()

    res = client.post(f"/api/v1/admin/notifications/rules/{rule.id}/evaluate", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["matchedUsers"] == 2
    assert data["notificationsCreated"] == 2
    assert data["emailsSent"] == 1

    emails = {m["to_email"] for m in get_sent_messages()}
    assert emails == {"optin@elizade.test"}


# --------------------------------------------------------------------------- #
# Campaigns                                                                   #
# --------------------------------------------------------------------------- #


def test_create_campaign_computes_reach(client, admin_headers, db_session):
    with_vehicle = _customer_with_prefs(db_session, "8100000301", "has@elizade.test", marketing_opt_in=False)
    _customer_with_prefs(db_session, "8100000302", "none@elizade.test", marketing_opt_in=False)
    _owned_vehicle(db_session, with_vehicle, days_until_service=20)

    res = client.post(
        "/api/v1/admin/notifications/campaigns",
        headers=admin_headers,
        json={
            "title": "Owners update",
            "body": "Important info for vehicle owners",
            "segmentKey": "has_vehicle",
            "channels": ["in_app"],
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["segmentKey"] == "has_vehicle"
    assert data["reachCount"] == 1
    assert data["status"] == "draft"


def test_send_campaign_delivers_and_is_idempotent(client, admin_headers, db_session, customer_user):
    campaign = BroadcastCampaign(
        title="All hands",
        body="Platform maintenance tonight",
        segment_key="all_customers",
        channels=["in_app", "email", "push"],
        status=BroadcastCampaignStatus.draft,
        reach_count=0,
    )
    db_session.add(campaign)
    db_session.commit()

    res = client.post(f"/api/v1/admin/notifications/campaigns/{campaign.id}/send", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "sent"
    assert data["reachCount"] >= 1
    assert data["notificationsCreated"] >= 1

    again = client.post(f"/api/v1/admin/notifications/campaigns/{campaign.id}/send", headers=admin_headers)
    assert again.status_code == 400


def test_marketing_campaign_skips_non_opted_in_email(client, admin_headers, db_session):
    opted_in = _customer_with_prefs(db_session, "8100000401", "m1@elizade.test", marketing_opt_in=True)
    _customer_with_prefs(db_session, "8100000402", "m2@elizade.test", marketing_opt_in=False)

    create = client.post(
        "/api/v1/admin/notifications/campaigns",
        headers=admin_headers,
        json={
            "title": "Promo",
            "body": "Limited offer",
            "segmentKey": "marketing_opt_in",
            "channels": ["in_app", "email"],
        },
    )
    campaign_id = create.json()["id"]

    send = client.post(f"/api/v1/admin/notifications/campaigns/{campaign_id}/send", headers=admin_headers)
    assert send.status_code == 200
    assert send.json()["emailsSent"] == 1
    assert {m["to_email"] for m in get_sent_messages()} == {"m1@elizade.test"}


# --------------------------------------------------------------------------- #
# Customer notification feed                                                  #
# --------------------------------------------------------------------------- #


def test_customer_lists_and_marks_notifications_read(client, customer_headers, db_session, customer_user):
    n1 = UserNotification(
        user_id=customer_user.id,
        title="A",
        body="First",
        category=NotificationCategory.system,
        is_read=False,
    )
    n2 = UserNotification(
        user_id=customer_user.id,
        title="B",
        body="Second",
        category=NotificationCategory.service,
        is_read=True,
    )
    db_session.add_all([n1, n2])
    db_session.commit()

    all_res = client.get("/api/v1/notifications", headers=customer_headers)
    assert all_res.status_code == 200
    assert len(all_res.json()) == 2

    unread_res = client.get("/api/v1/notifications?unreadOnly=true", headers=customer_headers)
    assert unread_res.status_code == 200
    assert len(unread_res.json()) == 1
    assert unread_res.json()[0]["title"] == "A"

    mark = client.post(f"/api/v1/notifications/{n1.id}/read", headers=customer_headers)
    assert mark.status_code == 200
    assert mark.json()["isRead"] is True

    unread_after = client.get("/api/v1/notifications?unreadOnly=true", headers=customer_headers)
    assert unread_after.json() == []


def test_customer_cannot_mark_another_users_notification(client, customer_headers, db_session, admin_user):
    other = UserNotification(
        user_id=admin_user.id,
        title="Admin only",
        body="Secret",
        category=NotificationCategory.system,
        is_read=False,
    )
    db_session.add(other)
    db_session.commit()

    res = client.post(f"/api/v1/notifications/{other.id}/read", headers=customer_headers)
    assert res.status_code == 404
