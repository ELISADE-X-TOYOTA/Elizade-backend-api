"""
Phase 1 — service operations KPIs:
    GET /api/v1/admin/service/stats
"""

from datetime import datetime, timedelta, timezone

from app.domains.shared.enums import AppointmentStatus

STATS_URL = "/api/v1/admin/service/stats"


def test_stats_requires_auth(client):
    assert client.get(STATS_URL).status_code == 401


def test_stats_rejects_customer(client, customer_headers):
    assert client.get(STATS_URL, headers=customer_headers).status_code == 403


def test_stats_allows_staff(client, staff_headers):
    resp = client.get(STATS_URL, headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json() == {"todaysAppointments": 0, "inProgress": 0, "awaitingApproval": 0, "completed": 0}


def test_stats_counts_today_by_status(client, staff_headers, appointment_factory):
    now = datetime.now(timezone.utc)
    appointment_factory(status=AppointmentStatus.confirmed, scheduled_at=now)
    appointment_factory(status=AppointmentStatus.in_progress, scheduled_at=now)
    appointment_factory(status=AppointmentStatus.awaiting_approval, scheduled_at=now)
    appointment_factory(status=AppointmentStatus.completed, scheduled_at=now)
    appointment_factory(status=AppointmentStatus.completed, scheduled_at=now)

    body = client.get(STATS_URL, headers=staff_headers).json()
    assert body["todaysAppointments"] == 5
    assert body["inProgress"] == 1
    assert body["awaitingApproval"] == 1
    assert body["completed"] == 2


def test_stats_excludes_other_days(client, staff_headers, appointment_factory):
    now = datetime.now(timezone.utc)
    appointment_factory(status=AppointmentStatus.confirmed, scheduled_at=now)
    appointment_factory(status=AppointmentStatus.confirmed, scheduled_at=now + timedelta(days=1))
    appointment_factory(status=AppointmentStatus.confirmed, scheduled_at=now - timedelta(days=1))

    body = client.get(STATS_URL, headers=staff_headers).json()
    assert body["todaysAppointments"] == 1
