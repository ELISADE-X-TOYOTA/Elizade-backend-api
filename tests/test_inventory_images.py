"""
Phase 3 — vehicle image endpoints:
    POST   /api/v1/admin/vehicles/{id}/images
    DELETE /api/v1/admin/vehicles/{id}/images/{imageId}

Storage is mocked (no disk I/O) so tests assert the service calls the backend
correctly and persists the returned URLs.
"""

import pytest

ADMIN_URL = "/api/v1/admin/vehicles"


@pytest.fixture
def fake_storage(monkeypatch):
    class FakeStorage:
        def __init__(self):
            self.saved = []
            self.deleted = []
            self._n = 0

        def save(self, *, content, filename, content_type):
            self._n += 1
            url = f"https://cdn.fake/{self._n}.jpg"
            self.saved.append({"url": url, "content": content, "filename": filename, "content_type": content_type})
            return url

        def delete(self, url):
            self.deleted.append(url)

    fake = FakeStorage()
    monkeypatch.setattr("app.domains.inventory.service.storage", fake)
    return fake


def _img(name="car.jpg", data=b"\x89PNG-bytes", content_type="image/jpeg"):
    return ("files", (name, data, content_type))


# --------------------------------------------------------------------------- #
# Upload                                                                       #
# --------------------------------------------------------------------------- #

def test_upload_requires_auth(client, vehicle_factory):
    v = vehicle_factory()
    assert client.post(f"{ADMIN_URL}/{v.id}/images", files=[_img()]).status_code == 401


def test_upload_rejects_staff(client, staff_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.post(f"{ADMIN_URL}/{v.id}/images", files=[_img()], headers=staff_headers)
    assert resp.status_code == 403


def test_upload_single_becomes_primary(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.post(f"{ADMIN_URL}/{v.id}/images", files=[_img()], headers=admin_headers)
    assert resp.status_code == 201
    images = resp.json()["images"]
    assert len(images) == 1
    assert images[0]["isPrimary"] is True
    assert images[0]["url"] == "https://cdn.fake/1.jpg"
    assert len(fake_storage.saved) == 1
    assert fake_storage.saved[0]["content_type"] == "image/jpeg"


def test_upload_multiple_sort_and_single_primary(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.post(
        f"{ADMIN_URL}/{v.id}/images",
        files=[_img("a.jpg"), _img("b.png", content_type="image/png")],
        headers=admin_headers,
    )
    assert resp.status_code == 201
    images = sorted(resp.json()["images"], key=lambda i: i["sortOrder"])
    assert [i["sortOrder"] for i in images] == [0, 1]
    assert [i["isPrimary"] for i in images] == [True, False]


def test_upload_appends_after_existing_and_not_primary(client, admin_headers, vehicle_factory, image_factory, fake_storage):
    v = vehicle_factory()
    image_factory(v, url="https://cdn.elizade.test/existing.jpg", sort_order=0, is_primary=True)
    resp = client.post(f"{ADMIN_URL}/{v.id}/images", files=[_img()], headers=admin_headers)
    assert resp.status_code == 201
    images = sorted(resp.json()["images"], key=lambda i: i["sortOrder"])
    assert len(images) == 2
    assert images[1]["sortOrder"] == 1
    assert images[1]["isPrimary"] is False  # existing primary is untouched
    assert images[0]["isPrimary"] is True


def test_upload_rejects_non_image(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.post(
        f"{ADMIN_URL}/{v.id}/images",
        files=[_img("doc.pdf", data=b"%PDF-1.4", content_type="application/pdf")],
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert fake_storage.saved == []  # nothing persisted


def test_upload_rejects_empty_file(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.post(f"{ADMIN_URL}/{v.id}/images", files=[_img(data=b"")], headers=admin_headers)
    assert resp.status_code == 400


def test_upload_missing_vehicle_404(client, admin_headers, fake_storage):
    resp = client.post(
        f"{ADMIN_URL}/00000000-0000-0000-0000-000000000000/images",
        files=[_img()],
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_upload_no_files_422(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    assert client.post(f"{ADMIN_URL}/{v.id}/images", headers=admin_headers).status_code == 422


# --------------------------------------------------------------------------- #
# Delete image                                                                 #
# --------------------------------------------------------------------------- #

def test_delete_image_ok(client, admin_headers, vehicle_factory, image_factory, fake_storage):
    v = vehicle_factory()
    img = image_factory(v, url="https://cdn.fake/x.jpg", is_primary=True)
    resp = client.delete(f"{ADMIN_URL}/{v.id}/images/{img.id}", headers=admin_headers)
    assert resp.status_code == 204
    assert fake_storage.deleted == ["https://cdn.fake/x.jpg"]
    detail = client.get(f"{ADMIN_URL}/{v.id}", headers=admin_headers).json()
    assert detail["images"] == []


def test_delete_primary_promotes_next(client, admin_headers, vehicle_factory, image_factory, fake_storage):
    v = vehicle_factory()
    primary = image_factory(v, url="https://cdn.fake/1.jpg", sort_order=0, is_primary=True)
    second = image_factory(v, url="https://cdn.fake/2.jpg", sort_order=1, is_primary=False)
    resp = client.delete(f"{ADMIN_URL}/{v.id}/images/{primary.id}", headers=admin_headers)
    assert resp.status_code == 204
    detail = client.get(f"{ADMIN_URL}/{v.id}", headers=admin_headers).json()
    assert len(detail["images"]) == 1
    assert detail["images"][0]["id"] == second.id
    assert detail["images"][0]["isPrimary"] is True


def test_delete_image_missing_404(client, admin_headers, vehicle_factory, fake_storage):
    v = vehicle_factory()
    resp = client.delete(
        f"{ADMIN_URL}/{v.id}/images/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_delete_image_wrong_vehicle_404(client, admin_headers, vehicle_factory, image_factory, fake_storage):
    v1 = vehicle_factory(model="One")
    v2 = vehicle_factory(model="Two")
    img = image_factory(v2)
    resp = client.delete(f"{ADMIN_URL}/{v1.id}/images/{img.id}", headers=admin_headers)
    assert resp.status_code == 404
    assert fake_storage.deleted == []  # not removed from storage


def test_delete_image_rejects_staff(client, staff_headers, vehicle_factory, image_factory, fake_storage):
    v = vehicle_factory()
    img = image_factory(v)
    resp = client.delete(f"{ADMIN_URL}/{v.id}/images/{img.id}", headers=staff_headers)
    assert resp.status_code == 403
