"""Phase 2 — Service Board price book import and read APIs."""

import io

ITEMS = "/api/v1/admin/service/items"
MODELS = "/api/v1/admin/service/price-book/models"
BOARD = "/api/v1/admin/service/price-book/board"
PREVIEW = "/api/v1/admin/service/price-book/import/preview"
PUBLISH = "/api/v1/admin/service/price-book/import/publish"
VERSIONS = "/api/v1/admin/service/price-book/versions"

HEADER = "vehicleModel,serviceItemCode,mileageBandKm,price"


def _create_item(client, admin_headers, code="engine-oil-filter", group="periodic"):
    resp = client.post(
        ITEMS,
        json={"code": code, "name": "Engine oil and filter", "group": group},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _csv_bytes(*rows, header=HEADER):
    return ("\n".join([header, *rows]) + "\n").encode()


def _post_csv(client, headers, content, url=PREVIEW):
    return client.post(url, files={"file": ("prices.csv", content, "text/csv")}, headers=headers)


def test_board_models_seeded_for_staff(client, staff_headers):
    body = client.get(MODELS, headers=staff_headers).json()
    assert len(body) >= 9
    names = {row["name"] for row in body}
    assert "Corolla" in names
    assert "Hilux" in names


def test_published_board_404_until_import(client, staff_headers):
    assert client.get(BOARD, headers=staff_headers).status_code == 404


def test_preview_requires_admin(client, staff_headers, admin_headers):
    _create_item(client, admin_headers)
    content = _csv_bytes("Corolla,engine-oil-filter,10000,35000")
    assert _post_csv(client, {}, content).status_code == 401
    assert _post_csv(client, staff_headers, content).status_code == 403


def test_preview_validates_unknown_model(client, admin_headers):
    _create_item(client, admin_headers)
    body = _post_csv(client, admin_headers, _csv_bytes("UnknownModel,engine-oil-filter,10000,35000")).json()
    assert body["valid"] == 0
    assert body["failed"] == 1
    assert "Unknown vehicle model" in body["errors"][0]["errors"][0]


def test_preview_validates_negative_price(client, admin_headers):
    _create_item(client, admin_headers)
    body = _post_csv(client, admin_headers, _csv_bytes("Corolla,engine-oil-filter,10000,-1")).json()
    assert body["failed"] == 1


def test_preview_validates_duplicate_cells(client, admin_headers):
    _create_item(client, admin_headers)
    content = _csv_bytes(
        "Corolla,engine-oil-filter,10000,35000",
        "Corolla,engine-oil-filter,10000,36000",
    )
    body = _post_csv(client, admin_headers, content).json()
    assert body["valid"] == 1
    assert body["failed"] == 1
    assert body["duplicateCellsInFile"] == 1


def test_publish_and_read_board(client, staff_headers, admin_headers):
    _create_item(client, admin_headers)
    _create_item(client, admin_headers, code="brake-pads", group="chassis")
    content = _csv_bytes(
        "Corolla,engine-oil-filter,10000,35000",
        "Corolla,brake-pads,,45000",
    )
    preview = _post_csv(client, admin_headers, content).json()
    assert preview["valid"] == 2
    assert preview["failed"] == 0

    published = _post_csv(client, admin_headers, content, url=PUBLISH).json()
    assert published["entryCount"] == 2
    assert published["versionNumber"] == 1

    board = client.get(BOARD, headers=staff_headers).json()
    assert board["version"]["status"] == "published"
    assert board["version"]["priceInclusive"] is True
    assert len(board["entries"]) == 2
    assert board["version"]["disclaimer"]

    versions = client.get(VERSIONS, headers=staff_headers).json()
    assert len(versions) == 1
    detail = client.get(f"{VERSIONS}/{published['versionId']}", headers=staff_headers).json()
    assert detail["entryCount"] == 2


def test_publish_archives_previous_version(client, staff_headers, admin_headers):
    _create_item(client, admin_headers)
    row = "Corolla,engine-oil-filter,10000,35000"
    first = _post_csv(client, admin_headers, _csv_bytes(row), url=PUBLISH).json()
    second = _post_csv(client, admin_headers, _csv_bytes(row.replace("35000", "38000")), url=PUBLISH).json()
    assert second["versionNumber"] == 2
    assert second["archivedPreviousVersionId"] == first["versionId"]

    versions = client.get(VERSIONS, headers=staff_headers).json()
    statuses = {v["id"]: v["status"] for v in versions}
    assert statuses[first["versionId"]] == "archived"
    assert statuses[second["versionId"]] == "published"

    board = client.get(BOARD, headers=staff_headers).json()
    assert board["version"]["versionNumber"] == 2
    assert board["entries"][0]["price"] == "38000.00"
