"""Customer service portal — appointments, tracking, additional work approval."""

from app.domains.shared.enums import AppointmentStatus

CUSTOMER_SERVICE = "/api/v1/service"
ADMIN_JOBS = "/api/v1/admin/service/jobs"
ADMIN_APPT = "/api/v1/admin/service/appointments"


def _start_job(client, staff_headers, appointment_factory, **appt_kw):
    appt = appointment_factory(status=AppointmentStatus.confirmed, **appt_kw)
    resp = client.patch(f"{ADMIN_APPT}/{appt.id}/status", json={"action": "start"}, headers=staff_headers)
    assert resp.status_code == 200
    return appt, resp.json()["job"]["id"]


def test_list_appointments_requires_auth(client):
    assert client.get(f"{CUSTOMER_SERVICE}/appointments").status_code == 401


def test_list_appointments_rejects_staff(client, staff_headers):
    assert client.get(f"{CUSTOMER_SERVICE}/appointments", headers=staff_headers).status_code == 403


def test_list_appointments_for_customer(client, customer_headers, appointment_factory, customer_user):
    appointment_factory()
    body = client.get(f"{CUSTOMER_SERVICE}/appointments", headers=customer_headers).json()
    assert len(body) >= 1
    assert body[0]["vehicleLabel"] == "2022 Toyota Corolla"
    assert body[0]["pendingAdditionalWork"] is False


def test_track_appointment_with_job(client, customer_headers, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    resp = client.get(f"{CUSTOMER_SERVICE}/appointments/{appt.id}/track", headers=customer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["appointment"]["id"] == appt.id
    assert body["job"]["id"] == job_id
    assert body["job"]["stagesTotal"] >= 1


def test_track_other_customer_appointment_404(
    client, customer_headers, staff_headers, appointment_factory, db_session,
):
    from app.domains.shared.enums import UserRole
    from conftest import _make_user

    other = _make_user(
        db_session,
        role=UserRole.customer,
        phone="8099988776",
        email="other@test.com",
        first="Other",
        last="User",
    )
    appt = appointment_factory(user_id=other.id)
    client.patch(f"{ADMIN_APPT}/{appt.id}/status", json={"action": "start"}, headers=staff_headers)
    assert client.get(f"{CUSTOMER_SERVICE}/appointments/{appt.id}/track", headers=customer_headers).status_code == 404


def test_customer_approves_additional_work(client, customer_headers, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{ADMIN_JOBS}/{job_id}/additional-work",
        json={"description": "Replace brake pads", "cost": 45000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]

    resp = client.patch(
        f"{CUSTOMER_SERVICE}/jobs/{job_id}/additional-work/{work_id}",
        json={"decision": "approve"},
        headers=customer_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["additionalWork"][0]["status"] == "approved"
    assert body["status"] == "in_progress"

    track = client.get(f"{CUSTOMER_SERVICE}/appointments/{appt.id}/track", headers=customer_headers).json()
    assert track["appointment"]["status"] == "in_progress"
    assert track["job"]["additionalWork"][0]["status"] == "approved"


def test_customer_rejects_additional_work(client, customer_headers, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{ADMIN_JOBS}/{job_id}/additional-work",
        json={"description": "Wiper blades", "cost": 10000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]

    resp = client.patch(
        f"{CUSTOMER_SERVICE}/jobs/{job_id}/additional-work/{work_id}",
        json={"decision": "reject"},
        headers=customer_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["additionalWork"][0]["status"] == "rejected"


def test_customer_cannot_respond_twice(client, customer_headers, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{ADMIN_JOBS}/{job_id}/additional-work",
        json={"description": "Filter", "cost": 8000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]

    client.patch(
        f"{CUSTOMER_SERVICE}/jobs/{job_id}/additional-work/{work_id}",
        json={"decision": "approve"},
        headers=customer_headers,
    )
    resp = client.patch(
        f"{CUSTOMER_SERVICE}/jobs/{job_id}/additional-work/{work_id}",
        json={"decision": "reject"},
        headers=customer_headers,
    )
    assert resp.status_code == 400


def test_list_marks_pending_additional_work(client, customer_headers, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    client.post(
        f"{ADMIN_JOBS}/{job_id}/additional-work",
        json={"description": "Alignment", "cost": 15000},
        headers=staff_headers,
    )
    rows = client.get(f"{CUSTOMER_SERVICE}/appointments", headers=customer_headers).json()
    match = next(r for r in rows if r["id"] == appt.id)
    assert match["pendingAdditionalWork"] is True
