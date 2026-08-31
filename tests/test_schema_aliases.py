"""Guards the camelCase request contract against a pydantic upgrade.

Every request schema pairs a snake_case Python field with a camelCase alias.
Written as `first_name: str | None = Field(alias="firstName")`, newer pydantic
attaches the `Field` to a single member of the union and silently DROPS the
alias — the client's `firstName` stops binding, the field reads `None`, and a
PATCH becomes a no-op instead of an error. Registration broke this way in
production while working locally, because pydantic was unpinned and the two
environments resolved different versions.

The fix is `Annotated[str | None, Field(alias="firstName")] = None`, which
attaches the metadata to the field rather than to a union member.

These are pure schema checks — no database required.
"""

import re
import warnings
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"

#: The shape that silently loses its alias.
VULNERABLE = re.compile(r"^\s+\w+:\s+[^=]+\|\s*None\s*=\s*Field\([^)]*alias=", re.M)
#: list[T] = Field(..., alias=...) drops the alias the same way on newer pydantic.
LIST_ALIAS_VULNERABLE = re.compile(r"^\s+\w+:\s+list\[[^\]]+\]\s*=\s*Field\([^)]*alias=", re.M)


def test_no_schema_uses_the_fragile_union_alias_form():
    """`x: T | None = Field(alias=...)` must not come back."""
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for match in VULNERABLE.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(APP_DIR.parent)}:{line_no}")
        for match in LIST_ALIAS_VULNERABLE.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(APP_DIR.parent)}:{line_no} (list alias)")

    assert not offenders, (
        "These fields put Field(alias=...) on a union or list type, where newer pydantic "
        "drops the alias. Use Annotated[T, Field(alias=...)] = None (or default_factory for lists):\n  "
        + "\n  ".join(offenders)
    )


def test_building_the_app_emits_no_alias_warnings():
    """A clean model build — the warning production was logging."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from app.main import app

        app.openapi()

    alias_warnings = [str(w.message) for w in caught if "alias" in str(w.message).lower()]
    assert not alias_warnings, "pydantic reported unused aliases:\n  " + "\n  ".join(alias_warnings)


# ── The contract itself: camelCase in, snake_case out ────────────────────


@pytest.mark.parametrize(
    "factory,payload,checks",
    [
        pytest.param(
            "app.domains.auth.schemas:OtpRequestIn",
            {"email": "a@b.com", "purpose": "register", "firstName": "John", "lastName": "Doe", "otherName": "K"},
            {"first_name": "John", "last_name": "Doe", "other_name": "K"},
            id="registration-names",
        ),
        pytest.param(
            "app.domains.inventory.schemas:VehicleUpdateIn",
            {"stockNumber": "SN-1", "colorHex": "#FFFFFF", "isPublished": True, "branchId": "b1"},
            {"stock_number": "SN-1", "color_hex": "#FFFFFF", "is_published": True, "branch_id": "b1"},
            id="vehicle-patch",
        ),
        pytest.param(
            "app.domains.users.schemas:UserPreferencesUpdateIn",
            {"pushEnabled": False, "smsEnabled": False, "emailEnabled": True, "marketingOptIn": True},
            {"push_enabled": False, "sms_enabled": False, "email_enabled": True, "marketing_opt_in": True},
            id="notification-preferences",
        ),
        pytest.param(
            "app.domains.service.schemas:AppointmentUpdateIn",
            {"bayId": "bay-1", "technicianId": "tech-1"},
            {"bay_id": "bay-1", "assigned_technician_id": "tech-1"},
            id="appointment-patch",
        ),
        pytest.param(
            "app.domains.warranty.schemas:ClaimUpdateIn",
            {"resolutionNotes": "Approved", "assignedToId": "u1"},
            {"resolution_notes": "Approved", "assigned_to_id": "u1"},
            id="claim-patch",
        ),
        pytest.param(
            "app.domains.ownership.schemas:OwnershipRequestCreateIn",
            {
                "vin": "JTDBT923405000003",
                "registrationNumber": "LAG-123",
                "customerNotes": "Purchased last month",
                "documentUrls": ["/media/documents/proof.pdf"],
            },
            {
                "registration_number": "LAG-123",
                "customer_notes": "Purchased last month",
                "document_urls": ["/media/documents/proof.pdf"],
            },
            id="ownership-create",
        ),
        pytest.param(
            "app.domains.ownership.schemas:DocumentsAppendIn",
            {"documentUrls": ["/media/documents/extra.pdf"]},
            {"document_urls": ["/media/documents/extra.pdf"]},
            id="ownership-documents-append",
        ),
        pytest.param(
            "app.domains.service.schemas:ServiceHistoryLineIn",
            {"serviceItemId": "item-1", "operation": "serviced"},
            {"service_item_id": "item-1", "operation": "serviced"},
            id="service-history-line",
        ),
        pytest.param(
            "app.domains.service.schemas:ServiceItemUpdateIn",
            {"sortOrder": 4, "isActive": False},
            {"sort_order": 4, "is_active": False},
            id="service-item-patch",
        ),
    ],
)
def test_camelcase_payloads_bind(factory, payload, checks):
    module_path, name = factory.split(":")
    module = __import__(module_path, fromlist=[name])
    model = getattr(module, name)(**payload)
    for attr, expected in checks.items():
        assert getattr(model, attr) == expected, f"{name}.{attr} did not bind from its alias"


def test_snake_case_still_binds():
    """`populate_by_name` keeps internal callers and tests working."""
    from app.domains.inventory.schemas import VehicleUpdateIn

    assert VehicleUpdateIn(stock_number="SN-2").stock_number == "SN-2"


def test_constraints_survived_the_rewrite():
    """Moving into Annotated must not drop min/max/gt validation."""
    from pydantic import ValidationError

    from app.domains.inventory.schemas import VehicleUpdateIn
    from app.domains.users.schemas import UserProfileUpdateIn

    with pytest.raises(ValidationError):
        VehicleUpdateIn(promotionalPrice=-5)  # gt=0
    with pytest.raises(ValidationError):
        UserProfileUpdateIn(firstName="x" * 200)  # max_length=100


def test_pydantic_is_pinned():
    """An unpinned pydantic is what let local and production diverge."""
    reqs = (APP_DIR.parent / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pydantic==", reqs, re.M), (
        "pydantic must be pinned explicitly, not inherited via fastapi"
    )
