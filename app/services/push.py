import sys
from abc import ABC, abstractmethod

_sent_pushes: list[dict[str, str]] = []


def get_sent_pushes() -> list[dict[str, str]]:
    return list(_sent_pushes)


def clear_sent_pushes() -> None:
    _sent_pushes.clear()


class PushService(ABC):
    @abstractmethod
    def send(self, *, user_id: str, title: str, body: str, deep_link: str | None = None) -> None:
        ...


class MockPushService(PushService):
    def send(self, *, user_id: str, title: str, body: str, deep_link: str | None = None) -> None:
        entry = {"user_id": user_id, "title": title, "body": body, "deep_link": deep_link or ""}
        _sent_pushes.append(entry)
        line = (
            f"\n{'=' * 48}\n"
            f"  ELIZADE CONNECT PUSH (mock)\n"
            f"  User:  {user_id}\n"
            f"  Title: {title}\n"
            f"  Body:  {body[:120]}{'…' if len(body) > 120 else ''}\n"
            f"{'=' * 48}\n"
        )
        print(line, file=sys.stdout, flush=True)


push_service: PushService = MockPushService()
