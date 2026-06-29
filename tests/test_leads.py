import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.domains.leads.models import Lead, LeadNote
from app.domains.shared.enums import LeadStatus
from app.domains.users.models import User, UserRole

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def other_staff_user(db_session) -> User:
    user = User(
        phone_normalized="8100000099",
        phone_display="08100000099",
        first_name="Femi",
        last_name="Otedola",
        email="femi@elizade.test",
        role=UserRole.staff,
        department="Sales",
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def inactive_staff_user(db_session) -> User:
    user = User(
        phone_normalized="8100000098",
        phone_display="08100000098",
        first_name="Deactivated",
        last_name="User",
        email="deactivated@elizade.test",
        role=UserRole.staff,
        department="Sales",
        is_verified=True,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def lead_factory(db_session):
    def _create(**overrides):
        defaults = {
            "customer_name": "John Doe",
            "phone": "08012345678",
            "email": "johndoe@example.com",
            "source": "website",
            "status": LeadStatus.new,
            "interested_model": "Camry",
            "value": Decimal("15000000.00"),
        }
        defaults.update(overrides)
        lead = Lead(**defaults)
        db_session.add(lead)
        db_session.commit()
        db_session.refresh(lead)
        return lead
    return _create


# ---------------------------------------------------------------------------
# Auth / RBAC Tests
# ---------------------------------------------------------------------------

def test_leads_endpoints_require_auth(client):
    urls = [
        ("GET", "/api/v1/admin/leads"),
        ("GET", "/api/v1/admin/leads/pipeline"),
        ("GET", "/api/v1/admin/leads/some-id"),
        ("POST", "/api/v1/admin/leads"),
        ("PATCH", "/api/v1/admin/leads/some-id"),
        ("PATCH", "/api/v1/admin/leads/some-id/status"),
        ("PATCH", "/api/v1/admin/leads/some-id/assign"),
        ("POST", "/api/v1/admin/leads/some-id/won"),
        ("POST", "/api/v1/admin/leads/some-id/lost"),
        ("GET", "/api/v1/admin/leads/some-id/notes"),
        ("POST", "/api/v1/admin/leads/some-id/notes"),
    ]
    for method, url in urls:
        if method == "GET":
            res = client.get(url)
        elif method == "POST":
            res = client.post(url, json={})
        elif method == "PATCH":
            res = client.patch(url, json={})
        assert res.status_code == 401, f"{method} {url} did not return 401"


def test_leads_endpoints_forbidden_for_customers(client, customer_headers):
    urls = [
        ("GET", "/api/v1/admin/leads"),
        ("GET", "/api/v1/admin/leads/pipeline"),
        ("GET", "/api/v1/admin/leads/some-id"),
        ("POST", "/api/v1/admin/leads"),
        ("PATCH", "/api/v1/admin/leads/some-id"),
        ("PATCH", "/api/v1/admin/leads/some-id/status"),
        ("PATCH", "/api/v1/admin/leads/some-id/assign"),
        ("POST", "/api/v1/admin/leads/some-id/won"),
        ("POST", "/api/v1/admin/leads/some-id/lost"),
        ("GET", "/api/v1/admin/leads/some-id/notes"),
        ("POST", "/api/v1/admin/leads/some-id/notes"),
    ]
    for method, url in urls:
        if method == "GET":
            res = client.get(url, headers=customer_headers)
        elif method == "POST":
            res = client.post(url, json={}, headers=customer_headers)
        elif method == "PATCH":
            res = client.patch(url, json={}, headers=customer_headers)
        assert res.status_code == 403, f"{method} {url} did not return 403"


# ---------------------------------------------------------------------------
# Create Lead Tests
# ---------------------------------------------------------------------------

def test_create_lead_success_minimal(client, staff_headers):
    payload = {
        "customerName": "Tunde Bakare",
        "phone": "08099887766",
        "source": "showroom walk-in",
        "interestedModel": "Hilux",
        "value": 35000000.00,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["customerName"] == "Tunde Bakare"
    assert data["phone"] == "08099887766"
    assert data["source"] == "showroom walk-in"
    assert data["interestedModel"] == "Hilux"
    assert float(data["value"]) == 35000000.00
    assert data["status"] == "new"
    assert data["assignedAgent"] is None
    assert data["customer"] is None
    assert data["vehicle"] is None


def test_create_lead_success_with_relations(
    client, staff_headers, customer_user, vehicle_factory, staff_user
):
    veh = vehicle_factory(make="Toyota", model="Prado", price=Decimal("85000000.00"))
    payload = {
        "customerName": "Tunde Bakare",
        "phone": "08099887766",
        "source": "referral",
        "interestedModel": "Prado",
        "value": 85000000.00,
        "notes": "Interested in bulletproof variant.",
        "customerId": customer_user.id,
        "vehicleId": veh.id,
        "assignedAgentId": staff_user.id,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["customer"]["id"] == customer_user.id
    assert data["vehicle"]["id"] == veh.id
    assert data["assignedAgent"]["id"] == staff_user.id
    assert data["notes"] == "Interested in bulletproof variant."


def test_create_lead_invalid_customer(client, staff_headers, staff_user):
    # Cannot link another staff member as the lead prospect (customer)
    payload = {
        "customerName": "Invalid Customer",
        "phone": "08099887766",
        "source": "referral",
        "interestedModel": "Prado",
        "customerId": staff_user.id,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 400
    assert "Invalid customer" in res.json()["detail"]


def test_create_lead_invalid_vehicle(client, staff_headers):
    payload = {
        "customerName": "Tunde Bakare",
        "phone": "08099887766",
        "source": "referral",
        "interestedModel": "Prado",
        "vehicleId": "00000000-0000-0000-0000-000000000000",
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 400
    assert "Invalid vehicle" in res.json()["detail"]


def test_create_lead_invalid_agent(client, staff_headers, customer_user):
    # Cannot assign a customer user as the sales agent
    payload = {
        "customerName": "Tunde Bakare",
        "phone": "08099887766",
        "source": "referral",
        "interestedModel": "Prado",
        "assignedAgentId": customer_user.id,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 400
    assert "Invalid agent" in res.json()["detail"]


def test_create_lead_deactivated_agent(client, staff_headers, inactive_staff_user):
    payload = {
        "customerName": "Tunde Bakare",
        "phone": "08099887766",
        "source": "referral",
        "interestedModel": "Prado",
        "assignedAgentId": inactive_staff_user.id,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 400
    assert "deactivated" in res.json()["detail"]


def test_create_lead_validation_errors(client, staff_headers):
    # Negative value
    payload = {
        "customerName": "Tunde",
        "phone": "08099887766",
        "source": "web",
        "interestedModel": "Camry",
        "value": -100.0,
    }
    res = client.post("/api/v1/admin/leads", json=payload, headers=staff_headers)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# List Leads & Filters Tests
# ---------------------------------------------------------------------------

def test_list_leads_pagination_and_sorting(client, staff_headers, lead_factory):
    lead_factory(customer_name="Lead A")
    lead_factory(customer_name="Lead B")
    lead_factory(customer_name="Lead C")

    res = client.get("/api/v1/admin/leads?page=1&size=2", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["pages"] == 2


def test_list_leads_filter_status(client, staff_headers, lead_factory):
    lead_factory(customer_name="New Lead", status=LeadStatus.new)
    lead_factory(customer_name="Contacted Lead", status=LeadStatus.contacted)

    res = client.get("/api/v1/admin/leads?status=contacted", headers=staff_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["customerName"] == "Contacted Lead"


def test_list_leads_filter_invalid_status(client, staff_headers):
    res = client.get("/api/v1/admin/leads?status=invalid_status", headers=staff_headers)
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]


def test_list_leads_filter_source(client, staff_headers, lead_factory):
    lead_factory(customer_name="Web Lead", source="website")
    lead_factory(customer_name="Showroom Lead", source="showroom")

    res = client.get("/api/v1/admin/leads?source=web", headers=staff_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["customerName"] == "Web Lead"


def test_list_leads_filter_agent(client, staff_headers, lead_factory, staff_user, other_staff_user):
    lead_factory(customer_name="Lead 1", assigned_agent_id=staff_user.id)
    lead_factory(customer_name="Lead 2", assigned_agent_id=other_staff_user.id)

    res = client.get(f"/api/v1/admin/leads?assignedAgentId={staff_user.id}", headers=staff_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["customerName"] == "Lead 1"


def test_list_leads_filter_branch(client, staff_headers, lead_factory, vehicle_factory, branch, db_session):
    # Branch 1
    veh1 = vehicle_factory(branch_id=branch.id)
    lead_factory(customer_name="Branch Lead", vehicle_id=veh1.id)

    # Branch 2
    from app.domains.branches.models import Branch
    from app.domains.shared.enums import BranchType
    branch2 = Branch(
        name="Elizade Ikeja",
        type=BranchType.both,
        city="Ikeja",
        state="Lagos",
        address="Ikeja, Lagos",
        phone="08000000001",
        is_active=True,
    )
    db_session.add(branch2)
    db_session.commit()
    db_session.refresh(branch2)

    veh2 = vehicle_factory(branch_id=branch2.id)
    lead_factory(customer_name="Ikeja Lead", vehicle_id=veh2.id)

    res = client.get(f"/api/v1/admin/leads?branchId={branch2.id}", headers=staff_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["customerName"] == "Ikeja Lead"


def test_list_leads_search(client, staff_headers, lead_factory):
    lead_factory(customer_name="Chinedu Okeke", phone="08055551111", email="chinedu@mail.com", interested_model="RAV4")
    lead_factory(customer_name="Amina Bello", phone="08033332222", email="amina@mail.com", interested_model="Corolla")

    # Search name
    res = client.get("/api/v1/admin/leads?q=Okeke", headers=staff_headers)
    assert len(res.json()["items"]) == 1
    assert res.json()["items"][0]["customerName"] == "Chinedu Okeke"

    # Search phone
    res = client.get("/api/v1/admin/leads?q=2222", headers=staff_headers)
    assert len(res.json()["items"]) == 1
    assert res.json()["items"][0]["customerName"] == "Amina Bello"

    # Search email
    res = client.get("/api/v1/admin/leads?q=chinedu@", headers=staff_headers)
    assert len(res.json()["items"]) == 1

    # Search model
    res = client.get("/api/v1/admin/leads?q=rav4", headers=staff_headers)
    assert len(res.json()["items"]) == 1


# ---------------------------------------------------------------------------
# Detail & Notes Tests
# ---------------------------------------------------------------------------

def test_get_lead_detail(client, staff_headers, lead_factory, customer_user, staff_user, vehicle_factory):
    veh = vehicle_factory()
    lead = lead_factory(
        customer_id=customer_user.id,
        assigned_agent_id=staff_user.id,
        vehicle_id=veh.id,
        notes="Important prospect notes.",
    )
    res = client.get(f"/api/v1/admin/leads/{lead.id}", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["customerName"] == "John Doe"
    assert data["notes"] == "Important prospect notes."
    assert data["customer"]["id"] == customer_user.id
    assert data["assignedAgent"]["id"] == staff_user.id
    assert data["vehicle"]["id"] == veh.id


def test_get_lead_detail_not_found(client, staff_headers):
    res = client.get("/api/v1/admin/leads/00000000-0000-0000-0000-000000000000", headers=staff_headers)
    assert res.status_code == 404


def test_lead_notes_crud(client, staff_headers, lead_factory, staff_user):
    lead = lead_factory()

    # List empty notes
    res = client.get(f"/api/v1/admin/leads/{lead.id}/notes", headers=staff_headers)
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Add a note
    payload = {"body": "First outreach done, prospect wants a test drive."}
    res = client.post(f"/api/v1/admin/leads/{lead.id}/notes", json=payload, headers=staff_headers)
    assert res.status_code == 201
    note_data = res.json()
    assert note_data["id"] is not None
    assert note_data["body"] == "First outreach done, prospect wants a test drive."
    assert note_data["authorId"] == staff_user.id

    # List again
    res = client.get(f"/api/v1/admin/leads/{lead.id}/notes", headers=staff_headers)
    assert len(res.json()) == 1
    assert res.json()[0]["body"] == "First outreach done, prospect wants a test drive."


# ---------------------------------------------------------------------------
# Update Lead Tests
# ---------------------------------------------------------------------------

def test_update_lead_fields(client, staff_headers, lead_factory, customer_user, vehicle_factory):
    lead = lead_factory(customer_name="Old Name", value=Decimal("1000.0"))
    veh = vehicle_factory()

    payload = {
        "customerName": "New Name",
        "value": 15000000.00,
        "notes": "Updated notes.",
        "customerId": customer_user.id,
        "vehicleId": veh.id,
    }
    res = client.patch(f"/api/v1/admin/leads/{lead.id}", json=payload, headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["customerName"] == "New Name"
    assert float(data["value"]) == 15000000.00
    assert data["notes"] == "Updated notes."
    assert data["customer"]["id"] == customer_user.id
    assert data["vehicle"]["id"] == veh.id

    # Nullify customer and vehicle
    nullify_payload = {
        "customerId": "",
        "vehicleId": "",
    }
    res = client.patch(f"/api/v1/admin/leads/{lead.id}", json=nullify_payload, headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["customer"] is None
    assert data["vehicle"] is None


# ---------------------------------------------------------------------------
# Assign Lead Tests
# ---------------------------------------------------------------------------

def test_assign_reassign_agent(client, staff_headers, lead_factory, staff_user, other_staff_user):
    lead = lead_factory(assigned_agent_id=None)

    # Assign
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/assign",
        json={"assignedAgentId": staff_user.id},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["assignedAgent"]["id"] == staff_user.id

    # Reassign
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/assign",
        json={"assignedAgentId": other_staff_user.id},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["assignedAgent"]["id"] == other_staff_user.id


# ---------------------------------------------------------------------------
# Status & State Machine Tests
# ---------------------------------------------------------------------------

def test_status_transitions_non_terminal(client, staff_headers, lead_factory):
    lead = lead_factory(status=LeadStatus.new)

    # new -> contacted
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "contacted", "notes": "Called, prospect picked up."},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "contacted"

    # Verify note was created
    notes_res = client.get(f"/api/v1/admin/leads/{lead.id}/notes", headers=staff_headers)
    assert len(notes_res.json()) == 1
    assert notes_res.json()[0]["body"] == "Called, prospect picked up."

    # contacted -> proposal
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "proposal"},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "proposal"

    # Back transition proposal -> contacted
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "contacted"},
        headers=staff_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "contacted"


def test_status_endpoint_rejects_terminal_statuses(client, staff_headers, lead_factory):
    lead = lead_factory(status=LeadStatus.new)

    # Cannot set won
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "won"},
        headers=staff_headers,
    )
    assert res.status_code == 422
    assert "Use the /won endpoint" in res.json()["detail"]

    # Cannot set lost
    res = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "lost"},
        headers=staff_headers,
    )
    assert res.status_code == 422
    assert "Use the /lost endpoint" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Mark Won / Lost Terminal Tests
# ---------------------------------------------------------------------------

def test_mark_won_success(client, staff_headers, lead_factory, vehicle_factory):
    lead = lead_factory(status=LeadStatus.negotiation)
    veh = vehicle_factory()

    payload = {
        "vehicleId": veh.id,
        "notes": "Customer made complete payment.",
    }
    res = client.post(f"/api/v1/admin/leads/{lead.id}/won", json=payload, headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "won"
    assert data["wonAt"] is not None
    assert data["vehicle"]["id"] == veh.id

    # Verify status change is terminal
    res_status = client.patch(
        f"/api/v1/admin/leads/{lead.id}/status",
        json={"status": "contacted"},
        headers=staff_headers,
    )
    assert res_status.status_code == 409
    assert "Terminal status cannot be changed" in res_status.json()["detail"]

    # Won lead won't allow mark lost directly
    res_lost = client.post(
        f"/api/v1/admin/leads/{lead.id}/lost",
        json={"lostReason": "Changed mind"},
        headers=staff_headers,
    )
    assert res_lost.status_code == 409


def test_mark_lost_success(client, staff_headers, lead_factory):
    lead = lead_factory(status=LeadStatus.negotiation)

    payload = {
        "lostReason": "Pricing too high",
        "notes": "Offered 5% discount but customer still declined.",
    }
    res = client.post(f"/api/v1/admin/leads/{lead.id}/lost", json=payload, headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "lost"
    assert data["lostAt"] is not None
    assert data["lostReason"] == "Pricing too high"

    # Cannot mark won directly
    res_won = client.post(
        f"/api/v1/admin/leads/{lead.id}/won",
        json={},
        headers=staff_headers,
    )
    assert res_won.status_code == 409


def test_mark_lost_missing_reason(client, staff_headers, lead_factory):
    lead = lead_factory(status=LeadStatus.negotiation)
    res = client.post(f"/api/v1/admin/leads/{lead.id}/lost", json={}, headers=staff_headers)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Pipeline KPIs & Summary Chart Tests
# ---------------------------------------------------------------------------

def test_pipeline_summary_stats(client, staff_headers, lead_factory, db_session):
    # Seed multiple leads in different states
    lead_factory(status=LeadStatus.new, value=Decimal("10000000.00"))
    lead_factory(status=LeadStatus.proposal, value=Decimal("20000000.00"))
    lead_factory(status=LeadStatus.won, value=Decimal("30000000.00"))
    lead_factory(status=LeadStatus.lost, value=Decimal("15000000.00"))

    res = client.get("/api/v1/admin/leads/pipeline", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["totalLeads"] == 4
    assert float(data["totalValue"]) == 75000000.00
    # Conversion rate = 1 / (1 + 1) * 100 = 50.0%
    assert data["conversionRate"] == 50.0
    assert data["newThisWeek"] == 4

    by_status = {item["status"]: float(item["value"]) for item in data["byStatus"]}
    assert by_status["new"] == 10000000.00
    assert by_status["proposal"] == 20000000.00
    assert by_status["won"] == 30000000.00
    assert by_status["lost"] == 15000000.00
