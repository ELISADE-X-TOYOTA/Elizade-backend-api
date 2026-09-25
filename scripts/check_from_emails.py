#!/usr/bin/env python3
"""Check which addresses Postmark accepts as SMTP From (Sender Signatures).

Uses the same Server API token as production (Railway SMTP_PASSWORD / POSTMARK_TOKEN).
Each address is probed with one API send; Postmark returns OK or a clear rejection.

  export POSTMARK_TOKEN='your-postmark-server-token'
  ./.venv/bin/python scripts/check_from_emails.py

  ./.venv/bin/python scripts/check_from_emails.py --to alieric28@gmail.com
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

POSTMARK_EMAIL = "https://api.postmarkapp.com/email"

DEFAULT_CANDIDATES = (
    "elizade@elizade.net",
    "contactelizade@gmail.com",
)


def probe_from(server_token: str, from_email: str, to_email: str) -> tuple[bool, str]:
    payload = {
        "From": f"Elizade Connect <{from_email}>",
        "To": to_email,
        "Subject": f"[From check] {from_email}",
        "TextBody": f"Postmark From check for {from_email}. You can ignore or delete this message.",
        "MessageStream": "outbound",
        "Tag": "from-check",
    }
    try:
        response = httpx.post(
            POSTMARK_EMAIL,
            json=payload,
            headers={
                "X-Postmark-Server-Token": server_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"

    if response.status_code == 200:
        mid = response.json().get("MessageID", "?")
        return True, f"can be used as From (test sent, MessageID {mid})"

    try:
        body = response.json()
        code = body.get("ErrorCode", response.status_code)
        msg = body.get("Message", response.text[:240])
    except Exception:  # noqa: BLE001
        code, msg = response.status_code, response.text[:240]
    return False, f"cannot be used as From — ErrorCode {code}: {msg}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Postmark for verified From addresses (no Elizade API needed).",
    )
    parser.add_argument(
        "--to",
        default="alieric28@gmail.com",
        help="Recipient for probe messages (default: alieric28@gmail.com)",
    )
    parser.add_argument(
        "addresses",
        nargs="*",
        default=list(DEFAULT_CANDIDATES),
        help=f"From addresses to check (default: {' '.join(DEFAULT_CANDIDATES)})",
    )
    args = parser.parse_args()

    token = (os.environ.get("POSTMARK_TOKEN") or os.environ.get("SMTP_PASSWORD") or "").strip()
    if not token:
        print(
            "Missing Postmark Server token.\n\n"
            "  export POSTMARK_TOKEN='…'   # same as Railway variable SMTP_PASSWORD\n"
            "  ./.venv/bin/python scripts/check_from_emails.py\n",
            file=sys.stderr,
        )
        return 1

    to_email = args.to.strip()
    print(f"Probe recipient: {to_email}\n")

    usable: list[str] = []
    for addr in args.addresses:
        addr = addr.strip().lower()
        ok, detail = probe_from(token, addr, to_email)
        label = "YES" if ok else "NO"
        print(f"  [{label}]  {addr}")
        print(f"         {detail}\n")
        if ok:
            usable.append(addr)

    if usable:
        print(f"Use on Railway: SMTP_FROM_EMAIL={usable[0]}")
        return 0
    print("None of these addresses are verified senders in Postmark yet.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
