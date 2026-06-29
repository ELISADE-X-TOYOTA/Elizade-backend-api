"""
Phase 3 — jobs:
    GET   /api/v1/admin/service/jobs/{job_id}
    PATCH /api/v1/admin/service/jobs/{job_id}/stages/{stage_id}
    POST  /api/v1/admin/service/jobs/{job_id}/additional-work
    PATCH /api/v1/admin/service/jobs/{job_id}/additional-work/{work_id}
"""

from app.domains.shared.enums import AppointmentStatus

APPT_URL = "/api/v1/admin/service/appointments"
JOBS_URL = "/api/v1/admin/service/jobs"


def _start_job(client, staff_headers, appointment_factory, **appt_kw):
    """Create a confirmed appointment and start it; return (appointment, job_id)."""
    appt = appointment_factory(status=AppointmentStatus.confirmed, **appt_kw)
    resp = client.patch(f"{APPT_URL}/{appt.id}/status", json={"action": "start"}, headers=staff_headers)
    assert resp.status_code == 200
    return appt, resp.json()["job"]["id"]


# --------------------------------------------------------------------------- #
# Get job                                                                      #
# --------------------------------------------------------------------------- #

def test_get_job_requires_auth(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    assert client.get(f"{JOBS_URL}/{job_id}").status_code == 401


def test_get_job_rejects_customer(client, staff_headers, customer_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    assert client.get(f"{JOBS_URL}/{job_id}", headers=customer_headers).status_code == 403


def test_get_job_ok(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    body = client.get(f"{JOBS_URL}/{job_id}", headers=staff_headers).json()
    assert body["id"] == job_id
    assert body["status"] == "in_progress"
    assert body["customerName"] == "Tunde Bello"
    assert body["vehicleLabel"] == "2022 Toyota Corolla"
    assert body["stagesTotal"] == 6
    assert body["stagesCompleted"] == 0
    assert body["additionalWork"] == []
    assert body["invoice"] is None


def test_get_job_not_found(client, staff_headers):
    assert client.get(f"{JOBS_URL}/00000000-0000-0000-0000-000000000000", headers=staff_headers).status_code == 404


# --------------------------------------------------------------------------- #
# Stages                                                                       #
# --------------------------------------------------------------------------- #

def test_mark_stage_complete(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    job = client.get(f"{JOBS_URL}/{job_id}", headers=staff_headers).json()
    stage_id = job["stages"][0]["id"]

    resp = client.patch(f"{JOBS_URL}/{job_id}/stages/{stage_id}", json={"completed": True}, headers=staff_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stagesCompleted"] == 1
    target = next(s for s in body["stages"] if s["id"] == stage_id)
    assert target["completed"] is True
    assert target["completedAt"] is not None


def test_unmark_stage(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    stage_id = client.get(f"{JOBS_URL}/{job_id}", headers=staff_headers).json()["stages"][0]["id"]
    client.patch(f"{JOBS_URL}/{job_id}/stages/{stage_id}", json={"completed": True}, headers=staff_headers)
    resp = client.patch(f"{JOBS_URL}/{job_id}/stages/{stage_id}", json={"completed": False}, headers=staff_headers)
    target = next(s for s in resp.json()["stages"] if s["id"] == stage_id)
    assert target["completed"] is False
    assert target["completedAt"] is None


def test_stage_not_in_job_404(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    resp = client.patch(
        f"{JOBS_URL}/{job_id}/stages/00000000-0000-0000-0000-000000000000",
        json={"completed": True},
        headers=staff_headers,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Additional work                                                              #
# --------------------------------------------------------------------------- #

def test_add_additional_work_pauses_for_approval(client, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    resp = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "Replace brake pads", "cost": 45000},
        headers=staff_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["additionalWork"]) == 1
    assert body["additionalWork"][0]["status"] == "pending_approval"
    assert body["additionalWork"][0]["cost"] == "45000.00"
    assert body["status"] == "awaiting_approval"
    # Appointment is moved to awaiting_approval too.
    appt_body = client.get(f"{APPT_URL}/{appt.id}", headers=staff_headers).json()
    assert appt_body["status"] == "awaiting_approval"


def test_add_additional_work_invalid_cost(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    resp = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "X", "cost": 0},
        headers=staff_headers,
    )
    assert resp.status_code == 422  # Field(gt=0)


def test_approve_additional_work_resumes_job(client, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "Replace brake pads", "cost": 45000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]

    resp = client.patch(
        f"{JOBS_URL}/{job_id}/additional-work/{work_id}",
        json={"status": "approved"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["additionalWork"][0]["status"] == "approved"
    assert body["additionalWork"][0]["customerRespondedAt"] is not None
    # No pending work left → job + appointment resume.
    assert body["status"] == "in_progress"
    appt_body = client.get(f"{APPT_URL}/{appt.id}", headers=staff_headers).json()
    assert appt_body["status"] == "in_progress"


def test_reject_additional_work(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "Wiper blades", "cost": 10000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]
    resp = client.patch(
        f"{JOBS_URL}/{job_id}/additional-work/{work_id}",
        json={"status": "rejected"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["additionalWork"][0]["status"] == "rejected"
    assert resp.json()["status"] == "in_progress"


def test_additional_work_invalid_status(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    work_id = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "X", "cost": 5000},
        headers=staff_headers,
    ).json()["additionalWork"][0]["id"]
    resp = client.patch(
        f"{JOBS_URL}/{job_id}/additional-work/{work_id}",
        json={"status": "maybe"},
        headers=staff_headers,
    )
    assert resp.status_code == 400


def test_additional_work_not_in_job_404(client, staff_headers, appointment_factory):
    _, job_id = _start_job(client, staff_headers, appointment_factory)
    resp = client.patch(
        f"{JOBS_URL}/{job_id}/additional-work/00000000-0000-0000-0000-000000000000",
        json={"status": "approved"},
        headers=staff_headers,
    )
    assert resp.status_code == 404


def test_add_work_to_completed_job_400(client, staff_headers, appointment_factory):
    appt, job_id = _start_job(client, staff_headers, appointment_factory)
    client.patch(f"{APPT_URL}/{appt.id}/status", json={"action": "complete"}, headers=staff_headers)
    resp = client.post(
        f"{JOBS_URL}/{job_id}/additional-work",
        json={"description": "Too late", "cost": 5000},
        headers=staff_headers,
    )
    assert resp.status_code == 400
