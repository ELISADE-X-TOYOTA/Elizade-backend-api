"""Every notification email is branded, not just the three with templates.

The ticket confirmation — the most common mail this system sends — arrived as
one unstyled sentence from an address on the build vendor's domain. That is
what a phishing attempt looks like, and it was the customer's first impression
of Elizade's transactional mail.

Rather than a template per event, the catalogue's own copy is dropped into one
shared shell, so a new event is branded the day it is added rather than the day
somebody remembers to write a template. Bespoke templates still win where the
content IS the point: a quotation with line items, a reservation receipt.
"""

import pytest

from app.domains.notifications import catalog
from app.domains.notifications.notify import notify
from app.services.email_templates import build_notification_html


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    from app.domains.notifications import notify as notify_module

    def capture(*, to_email, subject, body, category, html_body=None):
        sent.append({"subject": subject, "body": body, "category": category, "html": html_body})

    monkeypatch.setattr(notify_module.email_service, "send_notification", capture)
    return sent


def test_an_ordinary_notification_now_has_html(db_session, customer_user, outbox):
    """THE REPORTED GAP. This event had no template of its own."""
    notify(db_session, user=customer_user, event=catalog.TICKET_OPENED,
           context={"subject": "Warning light", "reference": "TKT-1012", "sla_hours": 4,
                    "ticket_id": "tk-1"})

    assert len(outbox) == 1
    html = outbox[0]["html"]
    assert html, "the email went out as bare plain text"
    assert "Elizade" in html
    assert "TKT-1012" in html


def test_the_plain_text_alternative_survives(db_session, customer_user, outbox):
    """Some clients only render text, and it is what a screen reader gets."""
    notify(db_session, user=customer_user, event=catalog.TICKET_OPENED,
           context={"subject": "Warning light", "reference": "TKT-1012", "sla_hours": 4,
                    "ticket_id": "tk-1"})

    assert outbox[0]["body"], "the text part must not be dropped"
    assert "<" not in outbox[0]["body"], "the text part must not be HTML"


def test_a_bespoke_template_is_not_overwritten(db_session, customer_user, outbox):
    """The quotation and reservation receipts carry content the shell cannot."""
    notify(db_session, user=customer_user, event=catalog.TICKET_OPENED,
           context={"subject": "S", "reference": "R", "sla_hours": 4, "ticket_id": "t"},
           email_html="<html>bespoke</html>")

    assert outbox[0]["html"] == "<html>bespoke</html>"


def test_security_mail_carries_no_call_to_action(db_session, customer_user, outbox):
    """An account alert is exactly the mail an attacker wants clicked."""
    notify(db_session, user=customer_user, event=catalog.CONTACT_DETAILS_CHANGED,
           context={"field": "email address"})

    html = outbox[0]["html"]
    assert "Talk to a sales adviser" not in html
    assert "Contact support" not in html


def test_sales_mail_does_carry_one(db_session, customer_user, outbox):
    notify(db_session, user=customer_user, event=catalog.QUOTATION_ISSUED,
           context={"vehicle_label": "2024 Corolla", "valid_until": "30 Sep 2026"})

    assert "Talk to a sales adviser" in outbox[0]["html"]


# ── The shell itself ─────────────────────────────────────────────────────


def test_the_shell_renders_a_detail_table():
    html = build_notification_html(
        title="Vehicle ready", body="Your car is ready.", customer_name="Ada",
        details=[("Vehicle", "2024 Corolla"), ("Branch", "Elizade Ikeja")],
    )
    assert "2024 Corolla" in html
    assert "Elizade Ikeja" in html


def test_the_shell_leaves_no_placeholders():
    html = build_notification_html(title="T", body="B")
    head = html.split("<style")[0]
    assert "{" not in head and "}" not in head, head[:200]


def test_the_cta_is_a_table_not_a_bare_anchor():
    """Outlook drops padding on inline anchors, which turns a button into
    underlined text sitting on a coloured smear. The colour has to be on a
    table cell, with the link inside it."""
    html = build_notification_html(
        title="T", body="B", cta_label="Contact support", cta_url="https://www.elizade.net"
    )
    compact = "".join(html.split())

    assert "<td" in html and "Contact support" in html
    assert "https://www.elizade.net" in html
    # The brand gold sits on a cell, not on the anchor.
    assert 'background-color:#F5B301;border-radius:10px;' in compact, (
        "the call to action must be a coloured table cell"
    )


def test_no_greeting_when_the_name_is_unknown():
    html = build_notification_html(title="T", body="B", customer_name="")
    assert "Hello," in html
    assert "Hello ," not in html


def test_every_catalogue_event_renders_through_the_shell():
    """A new event must be branded on the day it is added."""
    for event in catalog.ALL_EVENTS:
        html = build_notification_html(title=event.title, body=event.body)
        assert html.startswith("<!DOCTYPE"), event.key
        assert "Elizade" in html, event.key
