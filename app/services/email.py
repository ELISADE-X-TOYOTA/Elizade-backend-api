import sys
from abc import ABC, abstractmethod

_sent_messages: list[dict[str, str]] = []


def get_sent_messages() -> list[dict[str, str]]:
    return list(_sent_messages)


def clear_sent_messages() -> None:
    _sent_messages.clear()


class EmailService(ABC):
    @abstractmethod
    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        ...

    @abstractmethod
    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
    ) -> None:
        ...


class MockEmailService(EmailService):
    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        self.send_notification(
            to_email=to_email,
            subject=f"Elizade Connect verification code ({purpose})",
            body=f"Your verification code is {code}.",
            category="otp",
        )

    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
    ) -> None:
        entry = {
            "to_email": to_email,
            "subject": subject,
            "body": body,
            "category": category,
        }
        _sent_messages.append(entry)
        print(
            f"[EMAIL:MOCK] to={to_email} subject={subject!r} category={category}",
            file=sys.stdout,
            flush=True,
        )


email_service: EmailService = MockEmailService()
