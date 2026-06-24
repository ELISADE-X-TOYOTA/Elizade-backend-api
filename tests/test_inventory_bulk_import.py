"""
Phase 4 — bulk import endpoint:
    POST /api/v1/admin/vehicles/bulk-import   (CSV or XLSX, admin only)
"""

import io

import openpyxl

BULK_URL = "/api/v1/admin/vehicles/bulk-import"
HEADER = "model,trim,year,color,price,fuelType,transmission,engine,branchId"


def _valid_row(branch, model="Corolla"):
    return f"{model},LE,2024,White,25000000,Petrol,Automatic,1.8L,{branch.id}"


def _csv_bytes(*data_rows, header=HEADER):
    return ("\n".join([header, *data_rows]) + "\n").encode()


def _post_csv(client, headers, content, name="vehicles.csv", content_type="text/csv"):
    return client.post(BULK_URL, files={"file": (name, content, content_type)}, headers=headers)


def _xlsx_bytes(header, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Auth                                                                         #
# --------------------------------------------------------------------------- #

def test_bulk_requires_auth(client, branch):
    assert _post_csv(client, {}, _csv_bytes(_valid_row(branch))).status_code == 401


def test_bulk_rejects_staff(client, staff_headers, branch):
    assert _post_csv(client, staff_headers, _csv_bytes(_valid_row(branch))).status_code == 403


def test_bulk_rejects_customer(client, customer_headers, branch):
    assert _post_csv(client, customer_headers, _csv_bytes(_valid_row(branch))).status_code == 403


# --------------------------------------------------------------------------- #
# CSV                                                                          #
# --------------------------------------------------------------------------- #

def test_csv_happy_path(client, admin_headers, branch):
    content = _csv_bytes(_valid_row(branch, "Corolla"), _valid_row(branch, "Camry"))
    resp = _post_csv(client, admin_headers, content)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["created"] == 2
    assert body["failed"] == 0
    assert len(body["createdIds"]) == 2
    # Created rows are visible in the admin grid.
    listing = client.get("/api/v1/admin/vehicles", headers=admin_headers).json()
    assert listing["total"] == 2


def test_csv_partial_failure_reports_row_number(client, admin_headers, branch):
    bad_row = f",LE,2024,White,25000000,Petrol,Automatic,1.8L,{branch.id}"  # missing model
    content = _csv_bytes(_valid_row(branch), bad_row)
    body = _post_csv(client, admin_headers, content).json()
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 3  # header=1, valid=2, bad=3
    assert any("model" in m for m in body["errors"][0]["errors"])


def test_csv_invalid_price_is_validation_error(client, admin_headers, branch):
    bad_row = f"Corolla,LE,2024,White,notaprice,Petrol,Automatic,1.8L,{branch.id}"
    body = _post_csv(client, admin_headers, _csv_bytes(bad_row)).json()
    assert body["created"] == 0
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 2


def test_csv_invalid_branch(client, admin_headers, branch):
    bad_row = "Corolla,LE,2024,White,25000000,Petrol,Automatic,1.8L,00000000-0000-0000-0000-000000000000"
    body = _post_csv(client, admin_headers, _csv_bytes(bad_row)).json()
    assert body["failed"] == 1
    assert "Branch not found" in body["errors"][0]["errors"]


def test_csv_invalid_availability(client, admin_headers, branch):
    header = HEADER + ",availability"
    bad_row = f"Corolla,LE,2024,White,25000000,Petrol,Automatic,1.8L,{branch.id},banana"
    body = _post_csv(client, admin_headers, _csv_bytes(bad_row, header=header)).json()
    assert body["failed"] == 1
    assert any("availability" in m.lower() for m in body["errors"][0]["errors"])


def test_csv_duplicate_vin_within_file(client, admin_headers, branch):
    header = "vin," + HEADER
    row1 = f"DUPVIN00000000001,Corolla,LE,2024,White,25000000,Petrol,Automatic,1.8L,{branch.id}"
    row2 = f"DUPVIN00000000001,Camry,XLE,2024,Black,30000000,Petrol,Automatic,2.5L,{branch.id}"
    body = _post_csv(client, admin_headers, _csv_bytes(row1, row2, header=header)).json()
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 3
    assert "VIN already exists" in body["errors"][0]["errors"]


def test_csv_duplicate_vin_against_existing(client, admin_headers, branch, vehicle_factory):
    vehicle_factory(vin="EXISTING000000001")
    header = "vin," + HEADER
    row = f"EXISTING000000001,Corolla,LE,2024,White,25000000,Petrol,Automatic,1.8L,{branch.id}"
    body = _post_csv(client, admin_headers, _csv_bytes(row, header=header)).json()
    assert body["created"] == 0
    assert "VIN already exists" in body["errors"][0]["errors"]


def test_csv_header_only_no_rows(client, admin_headers):
    resp = _post_csv(client, admin_headers, (HEADER + "\n").encode())
    assert resp.status_code == 400


def test_csv_empty_file(client, admin_headers):
    resp = _post_csv(client, admin_headers, b"")
    assert resp.status_code == 400


def test_unsupported_file_type(client, admin_headers, branch):
    resp = _post_csv(client, admin_headers, _csv_bytes(_valid_row(branch)), name="data.txt", content_type="text/plain")
    # text/plain with a .txt name is not accepted (only .csv / .xlsx)
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# XLSX                                                                         #
# --------------------------------------------------------------------------- #

def test_xlsx_happy_path(client, admin_headers, branch):
    header = ["model", "trim", "year", "color", "price", "fuelType", "transmission", "engine", "branchId"]
    rows = [
        ["Corolla", "LE", 2024, "White", 25000000, "Petrol", "Automatic", "1.8L", branch.id],
        ["Camry", "XLE", 2024, "Black", 30000000, "Petrol", "Automatic", "2.5L", branch.id],
    ]
    content = _xlsx_bytes(header, rows)
    resp = client.post(
        BULK_URL,
        files={"file": ("vehicles.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["failed"] == 0


def test_xlsx_partial_failure(client, admin_headers, branch):
    header = ["model", "trim", "year", "color", "price", "fuelType", "transmission", "engine", "branchId"]
    rows = [
        ["Corolla", "LE", 2024, "White", 25000000, "Petrol", "Automatic", "1.8L", branch.id],
        [None, "LE", 2024, "White", 25000000, "Petrol", "Automatic", "1.8L", branch.id],  # missing model
    ]
    content = _xlsx_bytes(header, rows)
    resp = client.post(
        BULK_URL,
        files={"file": ("vehicles.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    body = resp.json()
    assert body["created"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 3
