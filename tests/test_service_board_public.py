"""Public Service Board read API — no authentication."""

PUBLIC = "/api/v1/service-board"


def test_public_price_board_requires_no_auth(client, staff_headers, admin_headers):
    assert client.get(f"{PUBLIC}/price-book").status_code == 404


def test_public_items_empty(client):
    assert client.get(f"{PUBLIC}/items").status_code == 200
    assert client.get(f"{PUBLIC}/items").json() == []


def test_public_board_after_publish(client, admin_headers):
    from tests.test_service_price_book import ITEMS, PUBLISH, _create_item, _csv_bytes, _post_csv

    _create_item(client, admin_headers)
    content = _csv_bytes("Corolla,engine-oil-filter,10000,35000")
    _post_csv(client, admin_headers, content, url=PUBLISH)

    board = client.get(f"{PUBLIC}/price-book").json()
    assert board["version"]["status"] == "published"
    assert len(board["entries"]) == 1

    models = client.get(f"{PUBLIC}/price-book/models").json()
    assert len(models) >= 9

    bands = client.get(f"{PUBLIC}/price-book/mileage-bands").json()
    assert 10_000 in bands
