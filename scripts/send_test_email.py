#!/usr/bin/env python3
"""Send one test message using the same Postmark/SMTP config as the API.

Usage (from repo root, with Postmark vars in .env or the shell):

  ./.venv/bin/python scripts/send_test_email.py you@example.com

Required env (see .env.example): POSTMARK_TOKEN or SMTP_PASSWORD, SMTP_HOST,
SMTP_FROM_EMAIL, USE_POSTMARK_API=true.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.email import (  # noqa: E402
    EmailDeliveryError,
    MockEmailService,
    build_email_service,
    mail_sender_warning,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a one-off deliverability test email.")
    parser.add_argument("to", help="Recipient address")
    parser.add_argument(
        "--subject",
        default="Elizade Connect — sender verification test",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    warning = mail_sender_warning()
    if warning:
        print(f"Config warning: {warning}", file=sys.stderr)

    print(f"From (SMTP_FROM_EMAIL): {settings.smtp_from_email}")
    print(f"Support (footer):         {settings.support_email}")
    print(f"Postmark HTTP API:        {settings.postmark_api_enabled}")
    print(f"SMTP fallback configured: {settings.smtp_configured}")

    service = build_email_service()
    if isinstance(service, MockEmailService):
        print(
            "\nNo mail credentials loaded — message was NOT sent.\n"
            "Add POSTMARK_TOKEN (and SMTP_HOST=smtp.postmarkapp.com) to .env,\n"
            "or export the same variables from Railway and re-run.",
            file=sys.stderr,
        )
        return 1

    body = (
        f"This is a manual deliverability test from the Elizade Connect API stack.\n\n"
        f"From address: {settings.smtp_from_email}\n"
        f"If this arrived, Postmark accepted the send for that sender.\n"
        f"Check Postmark → Activity for bounces and Microsoft/Gmail spam folders."
    )
    html = (
        f"<p>This is a manual deliverability test from the Elizade Connect API stack.</p>"
        f"<p><strong>From:</strong> {settings.smtp_from_email}</p>"
        f"<p>If this arrived, Postmark accepted the send for that sender.</p>"
    )

    try:
        service.send_notification(
            to_email=args.to.strip(),
            subject=args.subject,
            body=body,
            html_body=html,
            category="test",
        )
    except EmailDeliveryError as exc:
        print(f"\nSend failed: {exc}", file=sys.stderr)
        print("If Postmark rejected the From address, verify elizade@elizade.net in Postmark.", file=sys.stderr)
        return 1

    print(f"\nOK — request accepted by Postmark/SMTP for {args.to}.")
    print("Check inbox, spam, and Postmark Activity (Delivered vs Bounced).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
