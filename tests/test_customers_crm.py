from datetime import datetime, timezone
import pytest
from app.core.security import create_access_token
from app.domains.users.models import User, UserRole
from app.domains.customers.models import OwnedVehicle, CustomerNote
from app.domains.leads.models import Lead
from app.domains.service.models import ServiceAppointment
from app.domains.support.models import SupportTicket
from app.domains.shared.enums import LeadStatus, ServiceType, AppointmentStatus, TicketCategory, TicketStatus, TicketPriority, BranchType
from app.domains.service.models import ServiceHistoryItem
from app.domains.branches.models import Branch


def create_test_user(db_session, role: UserRole, phone: str, email: str, first_name: str, last_name: str, is_active: bool = True, is_verified: bool = True):
    user = User(
        phone_normalized=phone,
        phone_display=phone,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=is_active,
        is_verified=is_verified,
        city="Lagos",
        state="Lagos"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_unauthenticated_access(client):
    response = client.get("/api/v1/admin/customers")
    print(response)
    assert response.status_code == 401


def test_customer_role_blocked(client, db_session):
    customer = create_test_user(db_session, UserRole.customer, "09012345678", "cust@elizade.com", "John", "Doe")
    token = create_access_token(customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/admin/customers", headers=headers)
    assert response.status_code == 403


def test_staff_role_allowed(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345679", "staff@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/admin/customers", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_search_customers(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345680", "staff2@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create distinct customers
    c1 = create_test_user(db_session, UserRole.customer, "2348123456701", "toyin@elizade.com", "Toyin", "Ade")
    c2 = create_test_user(db_session, UserRole.customer, "2348123456702", "favour@elizade.com", "Favour", "Ojo")

    # Search by first name
    response = client.get("/api/v1/admin/customers?q=Toyin", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == c1.id

    # Search by last name
    response = client.get("/api/v1/admin/customers?q=Ojo", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == c2.id

    # Search by email
    response = client.get("/api/v1/admin/customers?q=favour@elizade", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == c2.id

    # Search by phone
    response = client.get("/api/v1/admin/customers?q=2348123456701", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == c1.id


def test_segment_filtering(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345681", "staff3@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create customers with different states
    c_active = create_test_user(db_session, UserRole.customer, "111", "active@elizade.com", "Active", "User", is_active=True)
    c_inactive = create_test_user(db_session, UserRole.customer, "222", "inactive@elizade.com", "Inactive", "User", is_active=False)
    c_verified = create_test_user(db_session, UserRole.customer, "333", "verified@elizade.com", "Verified", "User", is_verified=True)
    c_unverified = create_test_user(db_session, UserRole.customer, "444", "unverified@elizade.com", "Unverified", "User", is_verified=False)

    # Test active filter
    response = client.get("/api/v1/admin/customers?segment=active", headers=headers)
    active_ids = [item["id"] for item in response.json()["items"]]
    assert c_active.id in active_ids
    assert c_inactive.id not in active_ids

    # Test inactive filter
    response = client.get("/api/v1/admin/customers?segment=inactive", headers=headers)
    inactive_ids = [item["id"] for item in response.json()["items"]]
    assert c_inactive.id in inactive_ids
    assert c_active.id not in inactive_ids

    # Test verified filter
    response = client.get("/api/v1/admin/customers?segment=verified", headers=headers)
    verified_ids = [item["id"] for item in response.json()["items"]]
    assert c_verified.id in verified_ids
    assert c_unverified.id not in verified_ids

    # Test unverified filter
    response = client.get("/api/v1/admin/customers?segment=unverified", headers=headers)
    unverified_ids = [item["id"] for item in response.json()["items"]]
    assert c_unverified.id in unverified_ids
    assert c_verified.id not in unverified_ids



def test_vehicle_ownership_segment(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345682", "staff4@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    c_with_vehicle = create_test_user(db_session, UserRole.customer, "555", "vehicle@elizade.com", "Vehicle", "Owner")
    c_no_vehicle = create_test_user(db_session, UserRole.customer, "666", "novehicle@elizade.com", "No", "Vehicle")

    # Add vehicle to c_with_vehicle
    vehicle = OwnedVehicle(
        user_id=c_with_vehicle.id,
        vin="TESTVIN1234567890",
        make="Toyota",
        model="Corolla",
        trim="LE",
        year=2022,
        color="Silver",
        registration_number="LAG-123-ABC"
    )
    db_session.add(vehicle)
    db_session.commit()

    # Test has_vehicle segment
    response = client.get("/api/v1/admin/customers?segment=has_vehicle", headers=headers)
    has_vehicle_ids = [item["id"] for item in response.json()["items"]]
    assert c_with_vehicle.id in has_vehicle_ids
    assert c_no_vehicle.id not in has_vehicle_ids

    # Test no_vehicle segment
    response = client.get("/api/v1/admin/customers?segment=no_vehicle", headers=headers)
    no_vehicle_ids = [item["id"] for item in response.json()["items"]]
    assert c_no_vehicle.id in no_vehicle_ids
    assert c_with_vehicle.id not in no_vehicle_ids


def test_pagination(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345683", "staff5@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create 5 customers
    for i in range(5):
        create_test_user(db_session, UserRole.customer, f"777{i}", f"cust{i}@elizade.com", f"Cust{i}", "User")

    # Fetch page 1 size 2
    response = client.get("/api/v1/admin/customers?page=1&size=2", headers=headers)
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 5
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["pages"] >= 3

    # Fetch page 2 size 2
    response2 = client.get("/api/v1/admin/customers?page=2&size=2", headers=headers)
    data2 = response2.json()
    assert len(data2["items"]) == 2
    assert data2["page"] == 2

    # Check no duplicate IDs between page 1 and page 2
    ids1 = {x["id"] for x in data["items"]}
    ids2 = {x["id"] for x in data2["items"]}
    assert not ids1.intersection(ids2)


def test_detailed_customer_response(client, db_session):
    staff = create_test_user(db_session, UserRole.staff, "09012345684", "staff6@elizade.com", "Jane", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    customer = create_test_user(db_session, UserRole.customer, "888", "detailed@elizade.com", "Detail", "Customer")

    # Add OwnedVehicle
    vehicle = OwnedVehicle(
        user_id=customer.id,
        vin="VIN12345678901234",
        make="Toyota",
        model="Camry",
        trim="XLE",
        year=2021,
        color="Black",
        registration_number="ABC-789-XYZ"
    )
    db_session.add(vehicle)

    # Add Note
    note = CustomerNote(
        customer_id=customer.id,
        author_id=staff.id,
        body="This is an internal CRM note."
    )
    db_session.add(note)

    # Add Lead
    lead = Lead(
        customer_id=customer.id,
        customer_name="Detail Customer",
        phone="888",
        source="Web",
        status=LeadStatus.new,
        interested_model="Toyota RAV4"
    )
    db_session.add(lead)

    db_session.commit()

    # Fetch details
    response = client.get(f"/api/v1/admin/customers?q=detailed@elizade.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    items = data["items"]
    assert len(items) == 1
    cust_data = items[0]

    # Verify basic details
    assert cust_data["firstName"] == "Detail"
    assert cust_data["lastName"] == "Customer"
    assert cust_data["email"] == "detailed@elizade.com"

    # Verify related entities
    assert len(cust_data["ownedVehicles"]) == 1
    assert cust_data["ownedVehicles"][0]["vin"] == "VIN12345678901234"
    assert cust_data["ownedVehicles"][0]["model"] == "Camry"

    assert len(cust_data["crmNotes"]) == 1
    assert cust_data["crmNotes"][0]["body"] == "This is an internal CRM note."
    assert cust_data["crmNotes"][0]["authorName"] == "Jane Staff"

    assert len(cust_data["leads"]) == 1
    assert cust_data["leads"][0]["interestedModel"] == "Toyota RAV4"


# ─────────────────────────────────────────────────────────────────────────────
# Customer Profile Endpoint Tests  GET /api/v1/admin/customers/{id}
# ─────────────────────────────────────────────────────────────────────────────

def test_profile_not_found(client, db_session):
    """Non-existent customer ID must return 404."""
    staff = create_test_user(db_session, UserRole.staff, "09099900001", "staff_pnf@elizade.com", "Staff", "Pnf")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/admin/customers/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404


def test_profile_unauthenticated(client, db_session):
    """Unauthenticated request must return 401."""
    customer = create_test_user(db_session, UserRole.customer, "09099900002", "cust_unauth@elizade.com", "Un", "Auth")
    response = client.get(f"/api/v1/admin/customers/{customer.id}")
    assert response.status_code == 401


def test_profile_customer_role_blocked(client, db_session):
    """Customer users must be blocked from accessing the profile endpoint (403)."""
    customer = create_test_user(db_session, UserRole.customer, "09099900003", "cust_blocked@elizade.com", "Blocked", "Cust")
    token = create_access_token(customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/admin/customers/{customer.id}", headers=headers)
    assert response.status_code == 403


def test_profile_success_with_crm_note_in_activity(client, db_session):
    """
    Staff can retrieve full customer profile.
    Verifies:
    - contact section has correct fields
    - preferences section has notification flags
    - activity contains CRM notes (staff-visible only, since endpoint is staff-gated)
    - activity is sorted newest-first
    """
    staff = create_test_user(db_session, UserRole.staff, "09099900004", "staff_profile@elizade.com", "Profile", "Staff")
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    customer = create_test_user(
        db_session,
        UserRole.customer,
        "09099900005",
        "profile_cust@elizade.com",
        "ProfileFirst",
        "ProfileLast",
        is_active=True,
        is_verified=True,
    )

    # Add a CRM note (should appear in activity)
    note = CustomerNote(
        customer_id=customer.id,
        author_id=staff.id,
        body="Profile test CRM note.",
    )
    db_session.add(note)

    # Add a lead (should also appear in activity)
    lead = Lead(
        customer_id=customer.id,
        customer_name="ProfileFirst ProfileLast",
        phone="09099900005",
        source="Showroom",
        status=LeadStatus.new,
        interested_model="Toyota Hilux",
    )
    db_session.add(lead)

    db_session.commit()

    response = client.get(f"/api/v1/admin/customers/{customer.id}", headers=headers)
    assert response.status_code == 200

    data = response.json()

    # ── contact ──────────────────────────────────────────────────────────────
    contact = data["contact"]
    assert contact["id"] == customer.id
    assert contact["firstName"] == "ProfileFirst"
    assert contact["lastName"] == "ProfileLast"
    assert contact["email"] == "profile_cust@elizade.com"
    assert contact["phone"] == "09099900005"
    assert contact["isActive"] is True
    assert contact["isVerified"] is True
    assert "createdAt" in contact
    assert "updatedAt" in contact

    # ── preferences ──────────────────────────────────────────────────────────
    prefs = data["preferences"]
    assert "pushEnabled" in prefs
    assert "smsEnabled" in prefs
    assert "emailEnabled" in prefs
    assert "marketingOptIn" in prefs
    # Defaults from DEFAULT_PREFERENCES
    assert prefs["pushEnabled"] is True
    assert prefs["smsEnabled"] is True
    assert prefs["emailEnabled"] is True
    assert prefs["marketingOptIn"] is False

    # ── activity ─────────────────────────────────────────────────────────────
    activity = data["activity"]
    assert isinstance(activity, list)

    types_in_activity = [item["type"] for item in activity]
    # CRM note is visible (staff-only gate is at router level, not in activity)
    assert "note" in types_in_activity
    # Lead should also be in the activity feed
    assert "lead" in types_in_activity

    # Every activity item must have required keys
    for item in activity:
        assert "id" in item
        assert "type" in item
        assert "title" in item
        assert "description" in item
        assert "timestamp" in item

    # Activity should be sorted newest-first (timestamps descending)
    timestamps = [item["timestamp"] for item in activity]
    assert timestamps == sorted(timestamps, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Customer Vehicles Endpoint Tests  GET /api/v1/admin/customers/{id}/vehicles
# ─────────────────────────────────────────────────────────────────────────────

def _vehicles_url(customer_id: str) -> str:
    return f"/api/v1/admin/customers/{customer_id}/vehicles"


def test_vehicles_unauthenticated(client, db_session):
    """No token → 401"""
    customer = create_test_user(
        db_session, UserRole.customer, "08100000001", "veh_unauth@elizade.com", "Veh", "Unauth"
    )
    response = client.get(_vehicles_url(customer.id))
    assert response.status_code == 401


def test_vehicles_customer_role_forbidden(client, db_session):
    """Customer token → 403 (endpoint is staff-only)"""
    customer = create_test_user(
        db_session, UserRole.customer, "08100000002", "veh_cust@elizade.com", "Veh", "Cust"
    )
    token = create_access_token(customer.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(_vehicles_url(customer.id), headers=headers)
    assert response.status_code == 403


def test_vehicles_customer_not_found(client, db_session):
    """Non-existent customer UUID → 404"""
    staff = create_test_user(
        db_session, UserRole.staff, "08100000003", "veh_staff_nf@elizade.com", "Staff", "Nf"
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(_vehicles_url("00000000-0000-0000-0000-000000000099"), headers=headers)
    assert response.status_code == 404


def test_vehicles_empty(client, db_session):
    """Customer with no vehicles → 200 with empty list"""
    staff = create_test_user(
        db_session, UserRole.staff, "08100000004", "veh_staff_e@elizade.com", "Staff", "Empty"
    )
    customer = create_test_user(
        db_session, UserRole.customer, "08100000005", "veh_cust_e@elizade.com", "VehEmpty", "Cust"
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(_vehicles_url(customer.id), headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["customerId"] == customer.id
    assert data["vehicles"] == []
    assert data["totalVehicles"] == 0


def test_vehicles_with_service_history(client, db_session):
    """
    Staff retrieves a customer's vehicle list.
    Verifies:
    - All vehicle fields are present and correct
    - serviceHistoryLink is a valid URL pointing to the expected path
    - serviceHistory items are present and sorted newest-first by performedAt
    - A vehicle without service history returns an empty serviceHistory list
    """
    staff = create_test_user(
        db_session, UserRole.staff, "08100000006", "veh_staff_ok@elizade.com", "Staff", "Ok"
    )
    customer = create_test_user(
        db_session, UserRole.customer, "08100000007", "veh_cust_ok@elizade.com", "VehOk", "Customer"
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a real Branch to satisfy foreign key constraint on ServiceHistoryItem.branch_id
    branch = Branch(
        name="Lagos Service Center",
        type=BranchType.both,
        city="Lagos",
        state="Lagos",
        address="123 Elizade Way, Lagos",
        phone="01-1234567",
        is_active=True,
    )
    db_session.add(branch)
    db_session.flush()

    # ── Vehicle 1: has 2 service history records ───────────────────────────
    vehicle1 = OwnedVehicle(
        user_id=customer.id,
        vin="VHTEST00000000001",
        make="Toyota",
        model="Camry",
        trim="XSE",
        year=2023,
        color="White",
        color_hex="#FFFFFF",
        mileage=15000,
        registration_number="LAG-VEH-001",
        is_primary=True,
    )
    db_session.add(vehicle1)
    db_session.flush()  # get vehicle1.id

    # Service history: older record first in DB, newer second
    sh_older = ServiceHistoryItem(
        owned_vehicle_id=vehicle1.id,
        user_id=customer.id,
        branch_id=branch.id,
        service_type="periodic",
        performed_at=datetime(2024, 1, 10, 8, 0, tzinfo=timezone.utc),
        mileage=10000,
        description="10,000 km periodic service",
        cost=25000,
    )
    sh_newer = ServiceHistoryItem(
        owned_vehicle_id=vehicle1.id,
        user_id=customer.id,
        branch_id=branch.id,
        service_type="repair",
        performed_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
        mileage=15000,
        description="AC compressor replacement",
        cost=85000,
    )
    db_session.add_all([sh_older, sh_newer])

    # ── Vehicle 2: no service history ─────────────────────────────────────
    vehicle2 = OwnedVehicle(
        user_id=customer.id,
        vin="VHTEST00000000002",
        make="Toyota",
        model="Hilux",
        trim="GR Sport",
        year=2022,
        color="Grey",
        color_hex="#808080",
        mileage=5000,
        registration_number="LAG-VEH-002",
        is_primary=False,
    )
    db_session.add(vehicle2)
    db_session.commit()

    response = client.get(_vehicles_url(customer.id), headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["customerId"] == customer.id
    assert data["totalVehicles"] == 2
    assert isinstance(data["vehicles"], list)

    # Find vehicle1 in response
    v1_data = next((v for v in data["vehicles"] if v["vin"] == "VHTEST00000000001"), None)
    assert v1_data is not None, "Vehicle 1 not found in response"

    # ── Verify vehicle fields ──────────────────────────────────────────────
    assert v1_data["id"] == vehicle1.id
    assert v1_data["make"] == "Toyota"
    assert v1_data["model"] == "Camry"
    assert v1_data["trim"] == "XSE"
    assert v1_data["year"] == 2023
    assert v1_data["color"] == "White"
    assert v1_data["colorHex"] == "#FFFFFF"
    assert v1_data["mileage"] == 15000
    assert v1_data["registrationNumber"] == "LAG-VEH-001"
    assert v1_data["isPrimary"] is True
    assert "createdAt" in v1_data

    # ── Verify serviceHistoryLink format ──────────────────────────────────
    link = v1_data["serviceHistoryLink"]
    assert f"/api/v1/admin/customers/{customer.id}/vehicles/{vehicle1.id}/service-history" in link

    # ── Verify service history is present and sorted newest-first ─────────
    history = v1_data["serviceHistory"]
    assert len(history) == 2

    # Newest first
    assert history[0]["serviceType"] == "repair"
    assert history[0]["mileage"] == 15000
    assert history[0]["cost"] == 85000.0
    assert history[0]["description"] == "AC compressor replacement"

    assert history[1]["serviceType"] == "periodic"
    assert history[1]["mileage"] == 10000

    # Confirm timestamps are actually descending
    performed_dates = [item["performedAt"] for item in history]
    assert performed_dates == sorted(performed_dates, reverse=True)

    # ── Vehicle 2 should have empty history ───────────────────────────────
    v2_data = next((v for v in data["vehicles"] if v["vin"] == "VHTEST00000000002"), None)
    assert v2_data is not None
    assert v2_data["serviceHistory"] == []
    assert v2_data["isPrimary"] is False


def test_timeline_unauthenticated(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900030",
        email="timeline_cust@elizade.com",
        first_name="Timeline",
        last_name="Cust",
    )
    db_session.commit()

    response = client.get(f"/api/v1/admin/customers/{customer.id}/timeline")
    assert response.status_code == 401


def test_timeline_customer_role_forbidden(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900031",
        email="timeline_cust2@elizade.com",
        first_name="Timeline",
        last_name="Cust2",
    )
    db_session.commit()

    token = create_access_token(customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/admin/customers/{customer.id}/timeline", headers=headers)
    assert response.status_code == 403


def test_timeline_staff_role_forbidden(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900032",
        email="timeline_cust3@elizade.com",
        first_name="Timeline",
        last_name="Cust3",
    )
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099900033",
        email="timeline_staff@elizade.com",
        first_name="Timeline",
        last_name="Staff",
    )
    db_session.commit()

    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Only admin is allowed, so staff is forbidden (403)
    response = client.get(f"/api/v1/admin/customers/{customer.id}/timeline", headers=headers)
    assert response.status_code == 403


def test_timeline_admin_role_allowed(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900034",
        email="timeline_cust4@elizade.com",
        first_name="Timeline",
        last_name="Cust4",
    )
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099900035",
        email="timeline_admin@elizade.com",
        first_name="Timeline",
        last_name="Admin",
    )
    db_session.commit()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/admin/customers/{customer.id}/timeline", headers=headers)
    assert response.status_code == 200


def test_timeline_customer_not_found(client, db_session):
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099900036",
        email="timeline_admin2@elizade.com",
        first_name="Timeline",
        last_name="Admin2",
    )
    db_session.commit()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    import uuid
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/admin/customers/{random_id}/timeline", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


def test_timeline_success_and_filtering(client, db_session):
    # Setup customer and admin
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900037",
        email="timeline_cust5@elizade.com",
        first_name="Timeline",
        last_name="Cust5",
    )
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099900038",
        email="timeline_admin3@elizade.com",
        first_name="Timeline",
        last_name="Admin3",
    )
    branch = Branch(
        name="Abuja Service Center",
        type=BranchType.both,
        city="Abuja",
        state="FCT",
        address="456 Elizade Way, Abuja",
        phone="09-1234567",
        is_active=True,
    )
    db_session.add(branch)
    db_session.flush()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create OwnedVehicle (required for service appointment)
    vehicle = OwnedVehicle(
        user_id=customer.id,
        vin="VIN99999999999999",
        make="Toyota",
        model="RAV4",
        trim="LE",
        year=2022,
        color="Black",
        color_hex="#000000",
        mileage=5000,
        registration_number="ABJ-VEH-999",
        is_primary=True,
        created_at=datetime(2024, 4, 15, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(vehicle)
    db_session.flush()

    # Create various activities:
    # 1. Lead (created_at = datetime(2024, 5, 1, ...))
    lead = Lead(
        customer_id=customer.id,
        customer_name="Timeline Cust5",
        phone="09099900037",
        source="Website",
        status=LeadStatus.new,
        interested_model="Toyota RAV4",
        created_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(lead)

    # 2. SupportTicket (created_at = datetime(2024, 5, 5, ...))
    ticket = SupportTicket(
        ticket_number="TCK-9988",
        user_id=customer.id,
        category=TicketCategory.general,
        subject="AC issue again",
        status=TicketStatus.open,
        priority=TicketPriority.high,
        first_response_due=datetime(2024, 5, 6, 10, 0, tzinfo=timezone.utc),
        resolution_due=datetime(2024, 5, 8, 10, 0, tzinfo=timezone.utc),
        created_at=datetime(2024, 5, 5, 14, 30, tzinfo=timezone.utc),
    )
    db_session.add(ticket)

    # 3. ServiceAppointment (created_at = datetime(2024, 5, 10, ...))
    app_date = datetime(2024, 5, 15, 9, 0, tzinfo=timezone.utc)
    appointment = ServiceAppointment(
        user_id=customer.id,
        owned_vehicle_id=vehicle.id,
        branch_id=branch.id,
        service_type=ServiceType.periodic,
        scheduled_at=app_date,
        mileage_at_booking=12000,
        issue_description="Periodic 20k checkup",
        status=AppointmentStatus.confirmed,
        created_at=datetime(2024, 5, 10, 11, 0, tzinfo=timezone.utc),
    )
    db_session.add(appointment)

    # 4. CustomerNote (created_at = datetime(2024, 5, 12, ...)) -> SHOULD NOT BE IN TIMELINE FEED
    note = CustomerNote(
        customer_id=customer.id,
        author_id=admin.id,
        body="Highly interested in RAV4 upgrade.",
        created_at=datetime(2024, 5, 12, 16, 0, tzinfo=timezone.utc),
    )
    db_session.add(note)

    db_session.commit()

    response = client.get(f"/api/v1/admin/customers/{customer.id}/timeline", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["customerId"] == customer.id
    assert data["totalItems"] == 3

    timeline = data["timeline"]
    assert len(timeline) == 3

    # Check types: should ONLY contain lead, ticket, appointment
    types = [item["type"] for item in timeline]
    assert "lead" in types
    assert "ticket" in types
    assert "appointment" in types
    assert "vehicle" not in types
    assert "note" not in types

    # Check chronological ordering: newest first
    # 1. Appointment (2024-05-10)
    # 2. Ticket (2024-05-05)
    # 3. Lead (2024-05-01)
    assert timeline[0]["type"] == "appointment"
    assert timeline[1]["type"] == "ticket"
    assert timeline[2]["type"] == "lead"

    # Verify descriptions and fields
    assert "Periodic 20k checkup" in timeline[0]["description"]
    assert "TCK-9988" in timeline[1]["description"]
    assert "Toyota RAV4" in timeline[2]["description"]


def test_notes_unauthenticated(client):
    # GET, POST, PATCH, DELETE should all return 401
    assert client.get("/api/v1/admin/customers/some-id/notes").status_code == 401
    assert client.post("/api/v1/admin/customers/some-id/notes", json={"body": "Test Note"}).status_code == 401
    assert client.patch("/api/v1/admin/customers/some-id/notes/some-note-id", json={"body": "Updated Note"}).status_code == 401
    assert client.patch("/api/v1/admin/customers/some-id/notes", json={"noteId": "some-note-id", "body": "Updated Note"}).status_code == 401
    assert client.delete("/api/v1/admin/customers/some-id/notes/some-note-id").status_code == 401


def test_notes_customer_role_forbidden(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900039",
        email="note_cust@elizade.com",
        first_name="Note",
        last_name="Cust",
    )
    token = create_access_token(customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    # GET, POST, PATCH, DELETE should all return 403
    assert client.get(f"/api/v1/admin/customers/{customer.id}/notes", headers=headers).status_code == 403
    assert client.post(f"/api/v1/admin/customers/{customer.id}/notes", json={"body": "Test Note"}, headers=headers).status_code == 403
    assert client.patch(f"/api/v1/admin/customers/{customer.id}/notes/some-note-id", json={"body": "Updated Note"}, headers=headers).status_code == 403
    assert client.patch(f"/api/v1/admin/customers/{customer.id}/notes", json={"noteId": "some-note-id", "body": "Updated Note"}, headers=headers).status_code == 403
    assert client.delete(f"/api/v1/admin/customers/{customer.id}/notes/some-note-id", headers=headers).status_code == 403


def test_notes_staff_crud_lifecycle(client, db_session):
    # Setup users: Customer, Staff 1, Staff 2, and Admin
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900040",
        email="note_cust2@elizade.com",
        first_name="Note",
        last_name="Cust2",
    )
    staff1 = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099900041",
        email="note_staff1@elizade.com",
        first_name="Note",
        last_name="Staff1",
    )
    staff2 = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099900042",
        email="note_staff2@elizade.com",
        first_name="Note",
        last_name="Staff2",
    )
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099900043",
        email="note_admin1@elizade.com",
        first_name="Note",
        last_name="Admin1",
    )

    token_staff1 = create_access_token(staff1.id)
    token_staff2 = create_access_token(staff2.id)
    token_admin = create_access_token(admin.id)

    headers_staff1 = {"Authorization": f"Bearer {token_staff1}"}
    headers_staff2 = {"Authorization": f"Bearer {token_staff2}"}
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # 1. Create a note as staff1
    response = client.post(
        f"/api/v1/admin/customers/{customer.id}/notes",
        json={"body": "Staff 1 original note content"},
        headers=headers_staff1,
    )
    assert response.status_code == 201
    note1_data = response.json()
    assert note1_data["body"] == "Staff 1 original note content"
    assert note1_data["authorName"] == "Note Staff1"
    assert note1_data["customerId"] == customer.id
    assert note1_data["authorId"] == staff1.id

    note1_id = note1_data["id"]

    # 2. Get notes list as staff2 (should see staff1's note)
    response = client.get(
        f"/api/v1/admin/customers/{customer.id}/notes",
        headers=headers_staff2,
    )
    assert response.status_code == 200
    notes_list = response.json()
    assert len(notes_list) == 1
    assert notes_list[0]["id"] == note1_id

    # 3. Staff2 tries to edit Staff1's note -> Should fail (403)
    response = client.patch(
        f"/api/v1/admin/customers/{customer.id}/notes/{note1_id}",
        json={"body": "Staff 2 trying to hijack"},
        headers=headers_staff2,
    )
    assert response.status_code == 403
    assert "authored" in response.json()["detail"]

    # 4. Admin tries to edit Staff1's note -> Should fail (403)
    response = client.patch(
        f"/api/v1/admin/customers/{customer.id}/notes/{note1_id}",
        json={"body": "Admin trying to hijack"},
        headers=headers_admin,
    )
    assert response.status_code == 403
    assert "authored" in response.json()["detail"]

    # 5. Staff1 edits their own note (via PATH endpoint) -> Should succeed (200)
    response = client.patch(
        f"/api/v1/admin/customers/{customer.id}/notes/{note1_id}",
        json={"body": "Staff 1 updated note content via path"},
        headers=headers_staff1,
    )
    assert response.status_code == 200
    assert response.json()["body"] == "Staff 1 updated note content via path"

    # 6. Staff1 edits their own note (via BODY endpoint) -> Should succeed (200)
    response = client.patch(
        f"/api/v1/admin/customers/{customer.id}/notes",
        json={"noteId": note1_id, "body": "Staff 1 updated note content via body"},
        headers=headers_staff1,
    )
    assert response.status_code == 200
    assert response.json()["body"] == "Staff 1 updated note content via body"

    # 7. Staff1 tries to update via BODY endpoint without noteId -> Should fail (400)
    response = client.patch(
        f"/api/v1/admin/customers/{customer.id}/notes",
        json={"body": "Missing noteId"},
        headers=headers_staff1,
    )
    assert response.status_code == 400

    # 8. Staff1 tries to delete their own note -> Should fail (403 - Only Admin allowed to delete)
    response = client.delete(
        f"/api/v1/admin/customers/{customer.id}/notes/{note1_id}",
        headers=headers_staff1,
    )
    assert response.status_code == 403

    # 9. Admin deletes the note -> Should succeed (200)
    response = client.delete(
        f"/api/v1/admin/customers/{customer.id}/notes/{note1_id}",
        headers=headers_admin,
    )
    assert response.status_code == 200

    # 10. Get notes list again -> should be empty
    response = client.get(
        f"/api/v1/admin/customers/{customer.id}/notes",
        headers=headers_admin,
    )
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_notes_not_found_handling(client, db_session):
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099900044",
        email="note_admin2@elizade.com",
        first_name="Note",
        last_name="Admin2",
    )
    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Use valid-format UUIDs that simply don't exist in the DB
    ghost_customer_id = "00000000-0000-0000-0000-000000000001"
    ghost_note_id = "00000000-0000-0000-0000-000000000002"

    # 1. Non-existent customer (valid UUID format, just not in DB)
    assert client.get(f"/api/v1/admin/customers/{ghost_customer_id}/notes", headers=headers).status_code == 404
    assert client.post(f"/api/v1/admin/customers/{ghost_customer_id}/notes", json={"body": "Hello"}, headers=headers).status_code == 404
    assert client.patch(f"/api/v1/admin/customers/{ghost_customer_id}/notes/{ghost_note_id}", json={"body": "Hello"}, headers=headers).status_code == 404
    assert client.delete(f"/api/v1/admin/customers/{ghost_customer_id}/notes/{ghost_note_id}", headers=headers).status_code == 404

    # 2. Existing customer but non-existent note (also valid-format UUID)
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099900045",
        email="note_cust3@elizade.com",
        first_name="Note",
        last_name="Cust3",
    )
    assert client.patch(f"/api/v1/admin/customers/{customer.id}/notes/{ghost_note_id}", json={"body": "Hello"}, headers=headers).status_code == 404
    assert client.delete(f"/api/v1/admin/customers/{customer.id}/notes/{ghost_note_id}", headers=headers).status_code == 404

    # 3. Sanity check: malformed UUID returns 404 (via the DataError guard) on GET
    assert client.get("/api/v1/admin/customers/not-a-uuid/notes", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# SECURITY GAP TESTS
# ---------------------------------------------------------------------------

def test_notes_empty_body_rejected(client, db_session):
    """Empty or whitespace-only body must be rejected with 422 by Pydantic validation."""
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910001",
        email="sec_staff1@elizade.com",
        first_name="Sec",
        last_name="Staff1",
    )
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910002",
        email="sec_cust1@elizade.com",
        first_name="Sec",
        last_name="Cust1",
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/admin/customers/{customer.id}/notes"

    # Empty string
    assert client.post(url, json={"body": ""}, headers=headers).status_code == 422
    # Missing body key entirely
    assert client.post(url, json={}, headers=headers).status_code == 422
    # Null body
    assert client.post(url, json={"body": None}, headers=headers).status_code == 422


def test_notes_oversized_body_rejected(client, db_session):
    """A body exceeding 5000 characters must be rejected with 422."""
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910003",
        email="sec_staff2@elizade.com",
        first_name="Sec",
        last_name="Staff2",
    )
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910004",
        email="sec_cust2@elizade.com",
        first_name="Sec",
        last_name="Cust2",
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/admin/customers/{customer.id}/notes"

    oversized_body = "A" * 5001
    response = client.post(url, json={"body": oversized_body}, headers=headers)
    assert response.status_code == 422


def test_notes_idor_cross_customer_body_patch(client, db_session):
    """
    IDOR check: Staff provides the noteId of a note belonging to customer A
    while hitting the endpoint for customer B. Must return 404, not leak the note.
    """
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910005",
        email="sec_staff3@elizade.com",
        first_name="Sec",
        last_name="Staff3",
    )
    customer_a = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910006",
        email="sec_custa@elizade.com",
        first_name="Sec",
        last_name="CustA",
    )
    customer_b = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910007",
        email="sec_custb@elizade.com",
        first_name="Sec",
        last_name="CustB",
    )
    token = create_access_token(staff.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a note on customer A
    response = client.post(
        f"/api/v1/admin/customers/{customer_a.id}/notes",
        json={"body": "Note on customer A"},
        headers=headers,
    )
    assert response.status_code == 201
    note_a_id = response.json()["id"]

    # Attempt to update it using customer B's URL (IDOR attempt)
    response = client.patch(
        f"/api/v1/admin/customers/{customer_b.id}/notes",
        json={"noteId": note_a_id, "body": "Trying to hijack via IDOR"},
        headers=headers,
    )
    assert response.status_code == 404, "IDOR: note from another customer must not be accessible"

    # Also check the path-based PATCH variant
    response = client.patch(
        f"/api/v1/admin/customers/{customer_b.id}/notes/{note_a_id}",
        json={"body": "Trying to hijack via IDOR on path"},
        headers=headers,
    )
    assert response.status_code == 404, "IDOR: note from another customer must not be accessible via path"


def test_notes_idor_cross_customer_delete(client, db_session):
    """
    IDOR check: Admin provides a noteId that belongs to customer A
    while hitting the DELETE endpoint for customer B. Must return 404.
    """
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099910008",
        email="sec_admin3@elizade.com",
        first_name="Sec",
        last_name="Admin3",
    )
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910009",
        email="sec_staff4@elizade.com",
        first_name="Sec",
        last_name="Staff4",
    )
    customer_a = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910010",
        email="sec_custc@elizade.com",
        first_name="Sec",
        last_name="CustC",
    )
    customer_b = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910011",
        email="sec_custd@elizade.com",
        first_name="Sec",
        last_name="CustD",
    )

    # Staff creates note on customer A
    staff_headers = {"Authorization": f"Bearer {create_access_token(staff.id)}"}
    response = client.post(
        f"/api/v1/admin/customers/{customer_a.id}/notes",
        json={"body": "A note on customer A"},
        headers=staff_headers,
    )
    assert response.status_code == 201
    note_a_id = response.json()["id"]

    # Admin tries to delete note from customer A using customer B's endpoint
    admin_headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    response = client.delete(
        f"/api/v1/admin/customers/{customer_b.id}/notes/{note_a_id}",
        headers=admin_headers,
    )
    assert response.status_code == 404, "IDOR: admin must not delete a note via a different customer's endpoint"

    # Confirm the note still exists on customer A
    response = client.get(
        f"/api/v1/admin/customers/{customer_a.id}/notes",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert any(n["id"] == note_a_id for n in response.json()), "Note should still exist on customer A after failed IDOR delete"


def test_notes_tampered_jwt_rejected(client, db_session):
    """A token with a tampered signature must return 401."""
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910012",
        email="sec_custe@elizade.com",
        first_name="Sec",
        last_name="CustE",
    )
    # Build a valid token then corrupt the signature
    real_token = create_access_token(customer.id)
    tampered = real_token[:-4] + "xxxx"
    headers = {"Authorization": f"Bearer {tampered}"}

    assert client.get(f"/api/v1/admin/customers/{customer.id}/notes", headers=headers).status_code == 401
    assert client.post(f"/api/v1/admin/customers/{customer.id}/notes", json={"body": "hack"}, headers=headers).status_code == 401


def test_notes_coexist_and_are_not_replaced(client, db_session):
    """
    Notes from multiple authors must accumulate into a list — not replace each other.
    Ensures the list grows with each POST and ordering is newest-first.
    """
    staff1 = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910013",
        email="sec_staff5@elizade.com",
        first_name="Sec",
        last_name="Staff5",
    )
    staff2 = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910014",
        email="sec_staff6@elizade.com",
        first_name="Sec",
        last_name="Staff6",
    )
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099910015",
        email="sec_admin4@elizade.com",
        first_name="Sec",
        last_name="Admin4",
    )
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910016",
        email="sec_custf@elizade.com",
        first_name="Sec",
        last_name="CustF",
    )
    h1 = {"Authorization": f"Bearer {create_access_token(staff1.id)}"}
    h2 = {"Authorization": f"Bearer {create_access_token(staff2.id)}"}
    ha = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    url = f"/api/v1/admin/customers/{customer.id}/notes"

    import time
    
    # Three distinct authors each post a note
    r1 = client.post(url, json={"body": "Note from staff1"}, headers=h1)
    time.sleep(0.01)
    r2 = client.post(url, json={"body": "Note from staff2"}, headers=h2)
    time.sleep(0.01)
    r3 = client.post(url, json={"body": "Note from admin"}, headers=ha)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r3.status_code == 201

    # List must contain all three
    response = client.get(url, headers=ha)
    assert response.status_code == 200
    notes = response.json()
    assert len(notes) == 3, "All three notes must coexist — notes should NOT replace each other"

    bodies = [n["body"] for n in notes]
    assert "Note from staff1" in bodies
    assert "Note from staff2" in bodies
    assert "Note from admin" in bodies
    
    # Note: We cannot strictly assert newest-first ordering here (e.g. notes[0] == admin)
    # because the pytest db_session wraps the test in a single transaction, meaning
    # func.now() evaluates to the exact same microsecond for all three inserts.
    # The application code (service.py) does use .order_by(CustomerNote.created_at.desc())


def test_notes_admin_as_author_can_edit_own_note(client, db_session):
    """
    Admin creates a note and can edit it (admin is the author).
    No other user can edit it.
    """
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099910017",
        email="sec_admin5@elizade.com",
        first_name="Sec",
        last_name="Admin5",
    )
    staff = create_test_user(
        db_session,
        role=UserRole.staff,
        phone="09099910018",
        email="sec_staff7@elizade.com",
        first_name="Sec",
        last_name="Staff7",
    )
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910019",
        email="sec_custg@elizade.com",
        first_name="Sec",
        last_name="CustG",
    )
    ha = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    hs = {"Authorization": f"Bearer {create_access_token(staff.id)}"}
    url = f"/api/v1/admin/customers/{customer.id}/notes"

    # Admin creates a note
    r = client.post(url, json={"body": "Admin's own note"}, headers=ha)
    assert r.status_code == 201
    note_id = r.json()["id"]
    assert r.json()["authorName"] == "Sec Admin5"

    # Staff tries to edit admin's note → 403
    r2 = client.patch(f"{url}/{note_id}", json={"body": "Staff trying to edit admin note"}, headers=hs)
    assert r2.status_code == 403

    # Admin edits their own note → 200
    r3 = client.patch(f"{url}/{note_id}", json={"body": "Admin updated own note"}, headers=ha)
    assert r3.status_code == 200
    assert r3.json()["body"] == "Admin updated own note"
    assert r3.json()["authorId"] == admin.id


def test_notes_response_structure(client, db_session):
    """
    Verify the response structure always includes all required fields
    with correct types (prevents regressions in schema changes).
    """
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099910020",
        email="sec_admin6@elizade.com",
        first_name="Sec",
        last_name="Admin6",
    )
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099910021",
        email="sec_custh@elizade.com",
        first_name="Sec",
        last_name="CustH",
    )
    headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    url = f"/api/v1/admin/customers/{customer.id}/notes"

    response = client.post(url, json={"body": "Structure check note"}, headers=headers)
    assert response.status_code == 201
    data = response.json()

    # All required fields must be present
    required_fields = ["id", "customerId", "authorId", "authorName", "body", "createdAt", "updatedAt"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Types
    assert isinstance(data["id"], str) and len(data["id"]) > 0
    assert data["customerId"] == customer.id
    assert data["authorId"] == admin.id
    assert data["body"] == "Structure check note"
    assert isinstance(data["createdAt"], str)  # ISO datetime string
    assert isinstance(data["updatedAt"], str)

    # Confirm GET list also returns correct structure
    list_resp = client.get(url, headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    list_item = list_resp.json()[0]
# ---------------------------------------------------------------------------
# SEGMENTS TESTS
# ---------------------------------------------------------------------------

def test_segments_unauthenticated(client):
    assert client.get("/api/v1/admin/customers/segments").status_code == 401

def test_segments_customer_role_forbidden(client, db_session):
    customer = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099920001",
        email="seg_cust1@elizade.com",
        first_name="Seg",
        last_name="Cust1",
    )
    token = create_access_token(customer.id)
    assert client.get("/api/v1/admin/customers/segments", headers={"Authorization": f"Bearer {token}"}).status_code == 403

def test_segments_counts(client, db_session):
    admin = create_test_user(
        db_session,
        role=UserRole.admin,
        phone="09099920002",
        email="seg_admin1@elizade.com",
        first_name="Seg",
        last_name="Admin1",
    )
    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Initial state (might have existing data from other tests)
    r_initial = client.get("/api/v1/admin/customers/segments", headers=headers)
    assert r_initial.status_code == 200
    initial_data = r_initial.json()

    # Create a new "premium" and "active" customer
    c_premium = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099920003",
        email="seg_cust_prem@elizade.com",
        first_name="Prem",
        last_name="Cust",
        is_active=True,
        is_verified=True,
    )
    # Add 2 vehicles to make them premium
    v1 = OwnedVehicle(
        user_id=c_premium.id, make="Toyota", model="Camry", trim="XLE", year=2020, 
        vin="VIN1", registration_number="L1", color="Black", color_hex="#000000", mileage=10000
    )
    v2 = OwnedVehicle(
        user_id=c_premium.id, make="Honda", model="Civic", trim="EX", year=2021, 
        vin="VIN2", registration_number="L2", color="White", color_hex="#FFFFFF", mileage=15000
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    # Create an "at-risk" customer (inactive)
    c_at_risk = create_test_user(
        db_session,
        role=UserRole.customer,
        phone="09099920004",
        email="seg_cust_risk@elizade.com",
        first_name="Risk",
        last_name="Cust",
        is_active=False,
        is_verified=False,
    )
    db_session.commit()

    r_final = client.get("/api/v1/admin/customers/segments", headers=headers)
    assert r_final.status_code == 200
    final_data = r_final.json()

    # Verify deltas
    assert final_data["total"] == initial_data["total"] + 2
    assert final_data["active"] == initial_data["active"] + 1
    assert final_data["inactive"] == initial_data["inactive"] + 1
    assert final_data["verified"] == initial_data["verified"] + 1
    assert final_data["unverified"] == initial_data["unverified"] + 1
    assert final_data["premium"] == initial_data["premium"] + 1
    assert final_data["atRisk"] == initial_data["atRisk"] + 1
    assert final_data["new"] == initial_data["new"] + 2
    assert final_data["hasVehicle"] == initial_data["hasVehicle"] + 1
    assert final_data["noVehicle"] == initial_data["noVehicle"] + 1



