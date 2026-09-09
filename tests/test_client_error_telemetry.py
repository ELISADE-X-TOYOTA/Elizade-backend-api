"""Recording what the app actually hit.

A tester reported "Elizade services are temporarily unavailable" across every
warranty screen. That message is the client's text for an HTTP 5xx, so
something genuinely failed — and there was no record of it anywhere. Driving
all the warranty endpoints against the live database for all 45 customer
accounts produced 135 requests and zero errors, so it could not be reproduced
and could not be explained.

The app had the hook the whole time: `setApiErrorReporter` was defined in
`src/api/client.ts`, its comment said the layout registered the real reporter,
and nothing ever called it. Every failure was computed, shown, and dropped.

This is the sink for it.
"""

from app.domains.telemetry.models import ClientErrorReport

TELEMETRY = "/api/v1/telemetry/client-errors"


def _one(**over):
    item = {
        "status": 500,
        "code": "server_error",
        "path": "/warranty/certificates",
        "method": "GET",
        "requestId": "req-abc123",
        "isNetwork": False,
        "durationMs": 812,
        "appVersion": "1.0.0",
        "platform": "ios",
    }
    item.update(over)
    return item


def test_a_failure_is_recorded(client, customer_headers, db_session):
    res = client.post(TELEMETRY, headers=customer_headers, json={"items": [_one()]})

    assert res.status_code == 202, res.text
    row = db_session.query(ClientErrorReport).one()
    assert row.status == 500
    assert row.path == "/warranty/certificates"
    assert row.request_id == "req-abc123"


def test_it_is_attributed_to_the_signed_in_customer(client, customer_headers, customer_user, db_session):
    client.post(TELEMETRY, headers=customer_headers, json={"items": [_one()]})
    assert db_session.query(ClientErrorReport).one().user_id == customer_user.id


def test_a_signed_out_failure_is_still_recorded(client, db_session):
    """THE ONE THAT MATTERS MOST. A failing sign-in has no user yet, and is
    exactly the failure worth having a record of."""
    res = client.post(TELEMETRY, json={"items": [_one(path="/auth/otp/request", method="POST")]})

    assert res.status_code == 202, res.text
    row = db_session.query(ClientErrorReport).one()
    assert row.user_id is None
    assert row.path == "/auth/otp/request"


def test_an_expired_token_does_not_lose_the_report(client, db_session):
    """Refusing a crash report over its credentials loses the report and helps
    nobody."""
    res = client.post(
        TELEMETRY,
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"items": [_one()]},
    )

    assert res.status_code == 202, res.text
    assert db_session.query(ClientErrorReport).count() == 1


def test_a_network_failure_records_status_zero(client, customer_headers, db_session):
    """No response at all is the case server logs cannot see."""
    client.post(
        TELEMETRY,
        headers=customer_headers,
        json={"items": [_one(status=0, code="client_timeout", isNetwork=True, requestId=None)]},
    )

    row = db_session.query(ClientErrorReport).one()
    assert row.status == 0
    assert row.is_network is True
    assert row.request_id is None


def test_a_batch_is_accepted_whole(client, customer_headers, db_session):
    items = [_one(path=f"/warranty/{n}") for n in ("certificates", "claims", "recalls")]
    res = client.post(TELEMETRY, headers=customer_headers, json={"items": items})

    assert res.json()["accepted"] == 3
    assert db_session.query(ClientErrorReport).count() == 3


def test_an_oversized_batch_is_refused(client, customer_headers, db_session):
    """A device coming back online must not be able to flush a thousand
    buffered failures in one request."""
    res = client.post(
        TELEMETRY, headers=customer_headers, json={"items": [_one() for _ in range(50)]}
    )

    assert res.status_code == 422
    assert db_session.query(ClientErrorReport).count() == 0


def test_an_empty_batch_is_refused(client, customer_headers):
    assert client.post(TELEMETRY, headers=customer_headers, json={"items": []}).status_code == 422


def test_a_nonsense_status_is_refused(client, customer_headers, db_session):
    res = client.post(TELEMETRY, headers=customer_headers, json={"items": [_one(status=9999)]})
    assert res.status_code == 422
    assert db_session.query(ClientErrorReport).count() == 0


def test_an_overlong_path_cannot_overflow_the_column(client, customer_headers):
    res = client.post(TELEMETRY, headers=customer_headers, json={"items": [_one(path="/x" * 400)]})
    assert res.status_code == 422


def test_reports_accumulate_rather_than_replace(client, customer_headers, db_session):
    client.post(TELEMETRY, headers=customer_headers, json={"items": [_one()]})
    client.post(TELEMETRY, headers=customer_headers, json={"items": [_one(status=503)]})

    statuses = sorted(r.status for r in db_session.query(ClientErrorReport).all())
    assert statuses == [500, 503]
