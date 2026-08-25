"""SMS transport.

`DEFAULT_PREFERENCES` has advertised `sms_enabled` since before any SMS code
existed, so the toggle was a promise the system could not keep. This closes
that: a mock that records and prints when no provider is configured, and a
Termii sender for production — Termii being the common choice for Nigerian
delivery, where the international aggregators route poorly.

Mirrors `services/email.py` deliberately: same mock/real split, same
`*DeliveryError`, so `notify()` treats every transport identically.
"""

import logging
import sys
from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings

logger = logging.getLogger("elizade.sms")

_sent_messages: list[dict[str, str]] = []


def get_sent_sms() -> list[dict[str, str]]:
    return list(_sent_messages)


def clear_sent_sms() -> None:
    _sent_messages.clear()


class SmsDeliveryError(RuntimeError):
    """Raised when a message could not be handed to the SMS gateway."""


def normalize_msisdn(raw: str) -> str:
    """Nigerian numbers to E.164 without the leading '+'.

    Customers enter `0803…`, `+234803…` and `234803…` interchangeably; gateways
    accept only one of those, so normalise rather than reject.
    """
    digits = "".join(c for c in raw if c.isdigit())
    if digits.startswith("234"):
        return digits
    if digits.startswith("0"):
        return "234" + digits[1:]
    if len(digits) == 10:  # bare subscriber number
        return "234" + digits
    return digits


class SmsService(ABC):
    @abstractmethod
    def send(self, *, to: str, body: str) -> None: ...


class MockSmsService(SmsService):
    """Records and prints. Used whenever no gateway is configured."""

    def send(self, *, to: str, body: str) -> None:
        msisdn = normalize_msisdn(to)
        _sent_messages.append({"to": msisdn, "body": body})
        print(
            f"\n{'=' * 48}\n"
            f"  ELIZADE CONNECT SMS (mock — no gateway)\n"
            f"  To:   {msisdn}\n"
            f"  Body: {body[:150]}{'…' if len(body) > 150 else ''}\n"
            f"{'=' * 48}\n",
            file=sys.stdout,
            flush=True,
        )


class TermiiSmsService(SmsService):
    def __init__(self, *, api_key: str, sender_id: str, base_url: str) -> None:
        self.api_key = api_key
        self.sender_id = sender_id
        self.base_url = base_url.rstrip("/")

    def send(self, *, to: str, body: str) -> None:
        msisdn = normalize_msisdn(to)
        try:
            response = httpx.post(
                f"{self.base_url}/api/sms/send",
                json={
                    "to": msisdn,
                    "from": self.sender_id,
                    "sms": body,
                    "type": "plain",
                    "channel": "generic",
                    "api_key": self.api_key,
                },
                timeout=20,
            )
        except httpx.HTTPError as exc:
            logger.exception("[SMS] gateway unreachable for %s", msisdn)
            raise SmsDeliveryError("Could not reach the SMS gateway.") from exc

        if response.status_code >= 400:
            # The key is in the request body — never echo the response wholesale.
            logger.error("[SMS] rejected for %s (HTTP %s)", msisdn, response.status_code)
            raise SmsDeliveryError("The SMS gateway rejected that message.")

        logger.info("[SMS] delivered to=%s", msisdn)


def build_sms_service() -> SmsService:
    settings = get_settings()
    if getattr(settings, "sms_configured", False):
        logger.info("[SMS] Termii transport active (sender %s)", settings.sms_sender_id)
        return TermiiSmsService(
            api_key=settings.sms_api_key,
            sender_id=settings.sms_sender_id,
            base_url=settings.sms_base_url,
        )
    logger.warning("[SMS] no gateway configured — messages are printed to the console.")
    return MockSmsService()


sms_service: SmsService = build_sms_service()
