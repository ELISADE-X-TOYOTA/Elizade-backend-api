"""
Phase 2 — appointments + lifecycle:
    GET   /api/v1/admin/service/appointments
    GET   /api/v1/admin/service/appointments/{id}
    PATCH /api/v1/admin/service/appointments/{id}
    PATCH /api/v1/admin/service/appointments/{id}/status   (confirm/start/complete/cancel)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domains.service.models import (
    AdditionalWorkRequest,
    ServiceHistoryItem,
    ServiceInvoice,
    ServiceJob,
    ServiceJobStage,
)
from app.domains.shared.enums import (
    AdditionalWorkStatus,
    AppointmentStatus,
    ServiceJobStatus,
    ServiceType,
)

URL = "/api/v1/admin/service/appointments"


# --------------------------------------------------------------------------- #
# Board                                                                        #
# --------------------------------------------------------------------------- #

def test_board_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_board_rejects_customer(client, customer_headers):
    assert client.get(URL, headers=customer_headers).status_code == 403


def test_board_lists_today(client, staff_headers, appointment_factory):
    appointment_factory(scheduled_at=datetime.now(timezone.utc))
    body = client.get(URL, headers=staff_headers).json()
    assert len(body) == 1
    row = body[0]
    assert row["customerName"] == "Tunde Bello"
    assert row["vehicleLabel"] == "2022 Toyota Corolla"
    assert row["jobId"] is None


def test_board_filters_by_status_and_bay(client, staff_headers, appointment_factory, service_bay_factory):
    bay = service_bay_factory(name="Bay A")
    appointment_factory(status=AppointmentStatus.confirmed, bay_id=bay.id)
    appointment_factory(status=AppointmentStatus.requested)
    by_status = client.get(URL, params={"status": "confirmed"}, headers=staff_headers).json()
    assert len(by_status) == 1 and by_status[0]["status"] == "confirmed"
    by_bay = client.get(URL, params={"bayId": bay.id}, headers=staff_headers).json()
    assert len(by_bay) == 1 and by_bay[0]["bayId"] == bay.id


def test_board_filter_by_date(client, staff_headers, appointment_factory):
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    appointment_factory(scheduled_at=tomorrow)
    today_body = client.get(URL, headers=staff_headers).json()
    assert today_body == []
    date_str = tomorrow.strftime("%Y-%m-%d")
    tomorrow_body = client.get(URL, params={"date": date_str}, headers=staff_headers).json()
    assert len(tomorrow_body) == 1


def test_board_invalid_date(client, staff_headers):
    assert client.get(URL, params={"date": "31-12-2026"}, headers=staff_headers).status_code == 400


# --------------------------------------------------------------------------- #
# Detail                                                                       #
# --------------------------------------------------------------------------- #

def test_detail_ok(client, staff_headers, appointment_factory):
    appt = appointment_factory()
    body = client.get(f"{URL}/{appt.id}", headers=staff_headers).json()
    assert body["id"] == appt.id
    assert body["issueDescription"] == "Periodic maintenance"
    assert body["job"] is None


def test_detail_not_found(client, staff_headers):
    assert client.get(f"{URL}/00000000-0000-0000-0000-000000000000", headers=staff_headers).status_code == 404


# --------------------------------------------------------------------------- #
# Update                                                                       #
# --------------------------------------------------------------------------- #

def test_update_bay_and_technician(client, staff_headers, appointment_factory, service_bay_factory, staff_user):
    appt = appointment_factory()
    bay = service_bay_factory(name="Bay B")
    resp = client.patch(
        f"{URL}/{appt.id}",
        json={"bayId": bay.id, "technicianId": staff_user.id},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bayId"] == bay.id
    assert body["technicianId"] == staff_user.id
    assert body["technicianName"] == "Sade Adewale"


def test_update_bay_wrong_branch(client, staff_headers, appointment_factory, db_session):
    from app.domains.branches.models import Branch
    from app.domains.service.models import ServiceBay
    from app.domains.shared.enums import BranchType

    other = Branch(name="Other", type=BranchType.service_centre, city="Abuja", state="FCT", address="x")
    db_session.add(other)
    db_session.commit()
    bay = ServiceBay(branch_id=other.id, name="Foreign Bay", is_active=True)
    db_session.add(bay)
    db_session.commit()
    db_session.refresh(bay)

    appt = appointment_factory()
    resp = client.patch(f"{URL}/{appt.id}", json={"bayId": bay.id}, headers=staff_headers)
    assert resp.status_code == 400


def test_update_invalid_technician(client, staff_headers, appointment_factory, customer_user):
    appt = appointment_factory()
    resp = client.patch(f"{URL}/{appt.id}", json={"technicianId": customer_user.id}, headers=staff_headers)
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Status lifecycle                                                             #
# --------------------------------------------------------------------------- #

def _act(client, headers, appt_id, action):
    return client.patch(f"{URL}/{appt_id}/status", json={"action": action}, headers=headers)


def test_confirm(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.requested)
    resp = _act(client, staff_headers, appt.id, "confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


def test_confirm_illegal_from_in_progress(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.in_progress)
    assert _act(client, staff_headers, appt.id, "confirm").status_code == 400


def test_invalid_action(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.requested)
    assert _act(client, staff_headers, appt.id, "teleport").status_code == 400


def test_start_creates_job_with_stages(client, staff_headers, appointment_factory, db_session):
    appt = appointment_factory(status=AppointmentStatus.confirmed, service_type=ServiceType.periodic)
    resp = _act(client, staff_headers, appt.id, "start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["job"] is not None
    assert body["job"]["status"] == "in_progress"

    job = db_session.query(ServiceJob).filter(ServiceJob.appointment_id == appt.id).one()
    stages = db_session.query(ServiceJobStage).filter(ServiceJobStage.job_id == job.id).all()
    assert len(stages) == 6  # periodic template
    assert stages[0].label == "Vehicle received"


def test_start_repair_template(client, staff_headers, appointment_factory, db_session):
    appt = appointment_factory(status=AppointmentStatus.confirmed, service_type=ServiceType.repair)
    _act(client, staff_headers, appt.id, "start")
    job = db_session.query(ServiceJob).filter(ServiceJob.appointment_id == appt.id).one()
    labels = [s.label for s in db_session.query(ServiceJobStage).filter(ServiceJobStage.job_id == job.id).all()]
    assert "Diagnosis" in labels


def test_start_illegal_from_requested(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.requested)
    assert _act(client, staff_headers, appt.id, "start").status_code == 400


def test_complete_generates_invoice_and_history(client, staff_headers, appointment_factory, db_session):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    _act(client, staff_headers, appt.id, "start")
    job = db_session.query(ServiceJob).filter(ServiceJob.appointment_id == appt.id).one()

    # An approved extra-work item should flow into the generated invoice.
    db_session.add(
        AdditionalWorkRequest(
            job_id=job.id,
            description="Brake pads",
            cost=Decimal("45000.00"),
            status=AdditionalWorkStatus.approved,
        )
    )
    # A rejected one should be excluded.
    db_session.add(
        AdditionalWorkRequest(
            job_id=job.id,
            description="Wiper blades",
            cost=Decimal("10000.00"),
            status=AdditionalWorkStatus.rejected,
        )
    )
    db_session.commit()

    resp = _act(client, staff_headers, appt.id, "complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["job"]["status"] == "completed"

    db_session.expire_all()
    invoice = db_session.query(ServiceInvoice).filter(ServiceInvoice.job_id == job.id).one()
    assert invoice.total == Decimal("45000.00")
    history = db_session.query(ServiceHistoryItem).filter(ServiceHistoryItem.appointment_id == appt.id).one()
    assert history.cost == Decimal("45000.00")
    assert history.service_type == "periodic"


def test_complete_without_extra_work_zero_invoice(client, staff_headers, appointment_factory, db_session):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    _act(client, staff_headers, appt.id, "start")
    _act(client, staff_headers, appt.id, "complete")
    job = db_session.query(ServiceJob).filter(ServiceJob.appointment_id == appt.id).one()
    invoice = db_session.query(ServiceInvoice).filter(ServiceInvoice.job_id == job.id).one()
    assert invoice.total == Decimal("0")


def test_complete_illegal_from_confirmed(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    assert _act(client, staff_headers, appt.id, "complete").status_code == 400


def test_cancel_cascades_to_job(client, staff_headers, appointment_factory, db_session):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    _act(client, staff_headers, appt.id, "start")
    resp = _act(client, staff_headers, appt.id, "cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    job = db_session.query(ServiceJob).filter(ServiceJob.appointment_id == appt.id).one()
    db_session.refresh(job)
    assert job.status == ServiceJobStatus.cancelled


def test_cancel_completed_is_illegal(client, staff_headers, appointment_factory):
    appt = appointment_factory(status=AppointmentStatus.confirmed)
    _act(client, staff_headers, appt.id, "start")
    _act(client, staff_headers, appt.id, "complete")
    assert _act(client, staff_headers, appt.id, "cancel").status_code == 400
