"""Push transport.

Two implementations behind one interface, chosen at import time:

* `MockPushService`   — records and prints. Used when push is not configured,
                        so the console still shows what would have been sent.
* `ExpoPushService`   — posts to Expo's push API, which fronts both APNs and
                        FCM. The app is an Expo build, so this avoids carrying
                        Apple and Google credentials separately.

Tokens live in `device_tokens`, keyed by token rather than by user: one person
may have a phone and a tablet, and a reinstall issues a fresh token for the
same device. Expo reports tokens it can no longer deliver to, and those rows are
pruned — a token that has been dead for months is a silent, permanent failure
otherwise.
"""

import logging
import sys
from abc import ABC, abstractmethod

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger("elizade.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
#: Expo accepts up to 100 messages per request.
_BATCH = 100

_sent_pushes: list[dict[str, str]] = []


def get_sent_pushes() -> list[dict[str, str]]:
    return list(_sent_pushes)


def clear_sent_pushes() -> None:
    _sent_pushes.clear()


class PushDeliveryError(RuntimeError):
    """Raised when a push could not be handed to the provider."""


def tokens_for_user(db: Session, user_id: str) -> list[str]:
    from app.domains.notifications.models import DeviceToken  # noqa: PLC0415 — avoids an import cycle

    rows = db.query(DeviceToken.token).filter(DeviceToken.user_id == user_id).all()
    return [r[0] for r in rows]


def drop_tokens(db: Session, tokens: list[str]) -> int:
    """Remove tokens the provider says are unreachable."""
    if not tokens:
        return 0
    from app.domains.notifications.models import DeviceToken  # noqa: PLC0415

    removed = (
        db.query(DeviceToken)
        .filter(DeviceToken.token.in_(tokens))
        .delete(synchronize_session=False)
    )
    db.commit()
    if removed:
        logger.info("[PUSH] pruned %s dead token(s)", removed)
    return removed


class PushService(ABC):
    @abstractmethod
    def send(
        self,
        *,
        user_id: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        db: Session | None = None,
    ) -> None: ...


class MockPushService(PushService):
    def send(
        self,
        *,
        user_id: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        db: Session | None = None,
    ) -> None:
        _sent_pushes.append(
            {"user_id": user_id, "title": title, "body": body, "deep_link": deep_link or ""}
        )
        print(
            f"\n{'=' * 48}\n"
            f"  ELIZADE CONNECT PUSH (mock)\n"
            f"  User:  {user_id}\n"
            f"  Title: {title}\n"
            f"  Body:  {body[:120]}{'…' if len(body) > 120 else ''}\n"
            f"{'=' * 48}\n",
            file=sys.stdout,
            flush=True,
        )


class ExpoPushService(PushService):
    def __init__(self, *, access_token: str | None = None) -> None:
        self.access_token = access_token

    def send(
        self,
        *,
        user_id: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        db: Session | None = None,
    ) -> None:
        if db is None:
            # Without a session there is nowhere to read tokens from. Treat as
            # a caller bug rather than silently doing nothing.
            raise PushDeliveryError("Push requires a database session to resolve device tokens")

        tokens = tokens_for_user(db, user_id)
        if not tokens:
            # Not an error: plenty of customers never grant push permission.
            logger.info("[PUSH] no device tokens for %s — skipping", user_id)
            return

        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        dead: list[str] = []
        for start in range(0, len(tokens), _BATCH):
            chunk = tokens[start : start + _BATCH]
            messages = [
                {
                    "to": token,
                    "title": title,
                    "body": body,
                    "sound": "default",
                    "data": {"deepLink": deep_link} if deep_link else {},
                }
                for token in chunk
            ]
            try:
                response = httpx.post(EXPO_PUSH_URL, json=messages, headers=headers, timeout=20)
            except httpx.HTTPError as exc:
                logger.exception("[PUSH] provider unreachable")
                raise PushDeliveryError("Could not reach the push service.") from exc

            if response.status_code >= 400:
                logger.error("[PUSH] provider rejected the batch (HTTP %s)", response.status_code)
                raise PushDeliveryError("The push service rejected that message.")

            # Expo answers per-message; a DeviceNotRegistered ticket means the
            # app was uninstalled or the token rotated.
            for token, ticket in zip(chunk, response.json().get("data", []), strict=False):
                if ticket.get("status") == "error":
                    detail = (ticket.get("details") or {}).get("error")
                    if detail == "DeviceNotRegistered":
                        dead.append(token)
                    else:
                        logger.warning("[PUSH] %s for %s", detail or ticket.get("message"), user_id)

        if dead:
            drop_tokens(db, dead)

        logger.info("[PUSH] delivered to=%s tokens=%s", user_id, len(tokens) - len(dead))


def build_push_service() -> PushService:
    settings = get_settings()
    if getattr(settings, "push_enabled", False):
        logger.info("[PUSH] Expo transport active")
        return ExpoPushService(access_token=settings.expo_access_token or None)
    logger.warning("[PUSH] not configured — notifications are printed to the console.")
    return MockPushService()


push_service: PushService = build_push_service()
