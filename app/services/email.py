import smtplib
import sys
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings
from app.services.email_templates import build_otp_html, build_otp_plain_text

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
            subject="Your Elizade Connect verification code",
            body=build_otp_plain_text(code=code, purpose=purpose),
            html_body=build_otp_html(code=code, purpose=purpose),
            category="otp",
        )

    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
        html_body: str | None = None,
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


class SmtpEmailService(EmailService):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls

    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        self.send_notification(
            to_email=to_email,
            subject="Your Elizade Connect verification code",
            body=build_otp_plain_text(code=code, purpose=purpose),
            html_body=build_otp_html(code=code, purpose=purpose),
            category="otp",
        )

    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
        html_body: str | None = None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(self.host, self.port, timeout=30) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_email, [to_email], msg.as_string())

        print(f"[EMAIL:SMTP] to={to_email} subject={subject!r} category={category}", file=sys.stdout, flush=True)


def build_email_service() -> EmailService:
    settings = get_settings()
    if settings.smtp_configured:
        return SmtpEmailService(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_email=settings.smtp_from_email,
            use_tls=settings.smtp_use_tls,
        )
    return MockEmailService()


email_service: EmailService = build_email_service()
