import logging
import smtplib
import sys
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from app.core.config import get_settings
from app.services.email_templates import build_otp_html, build_otp_plain_text

logger = logging.getLogger("elizade.email")

_sent_messages: list[dict[str, str]] = []


def get_sent_messages() -> list[dict[str, str]]:
    return list(_sent_messages)


def clear_sent_messages() -> None:
    _sent_messages.clear()


class EmailDeliveryError(RuntimeError):
    """Raised when a message could not be handed to the mail server.

    Callers translate this into a user-facing error: for OTP specifically, a
    silent failure is worse than an error, because the user would otherwise
    wait forever for a code that is never going to arrive.
    """


class EmailService(ABC):
    @abstractmethod
    def send_otp(self, to_email: str, code: str, purpose: str) -> None: ...

    @abstractmethod
    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
        html_body: str | None = None,
    ) -> None: ...


def _otp_payload(code: str, purpose: str) -> dict[str, str]:
    return {
        "subject": "Your Elizade Connect verification code",
        "body": build_otp_plain_text(code=code, purpose=purpose),
        "html_body": build_otp_html(code=code, purpose=purpose),
        "category": "otp",
    }


class MockEmailService(EmailService):
    """Used when SMTP isn't configured: records messages instead of sending."""

    def send_otp(self, to_email: str, code: str, purpose: str) -> None:
        self.send_notification(to_email=to_email, **_otp_payload(code, purpose))

    def send_notification(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        category: str,
        html_body: str | None = None,
    ) -> None:
        _sent_messages.append(
            {"to_email": to_email, "subject": subject, "body": body, "category": category}
        )
        logger.info("[EMAIL:MOCK] to=%s category=%s subject=%r", to_email, category, subject)
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
        self.send_notification(to_email=to_email, **_otp_payload(code, purpose))

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
        msg["From"] = formataddr(("Elizade Connect", self.from_email))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.from_email.split("@")[-1])
        # Transactional hints: keep OTP out of promotions tabs and stop
        # auto-responders (out-of-office) from replying to a no-reply address.
        msg["Auto-Submitted"] = "auto-generated"
        msg["X-Auto-Response-Suppress"] = "All"
        if category == "otp":
            msg["X-Entity-Ref-ID"] = msg["Message-ID"]

        # Order matters: last part wins in clients that support it, so the
        # plain-text alternative must be attached before the HTML.
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                if self.use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(self.username, self.password)
                refused = server.sendmail(self.from_email, [to_email], msg.as_string())
        except smtplib.SMTPAuthenticationError as exc:
            logger.error(
                "[EMAIL:SMTP] authentication rejected by %s:%s for user %r — check credentials",
                self.host,
                self.port,
                self.username,
            )
            raise EmailDeliveryError("Email service rejected our credentials.") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("[EMAIL:SMTP] recipient refused: %s", to_email)
            raise EmailDeliveryError("That email address was rejected by the mail server.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            # Covers connection refused, DNS failure, TLS errors and timeouts.
            logger.exception("[EMAIL:SMTP] delivery failed to %s via %s:%s", to_email, self.host, self.port)
            raise EmailDeliveryError("Could not reach the email service.") from exc

        if refused:
            logger.warning("[EMAIL:SMTP] partially refused: %s", refused)
            raise EmailDeliveryError("That email address was rejected by the mail server.")

        logger.info(
            "[EMAIL:SMTP] delivered to=%s category=%s subject=%r via=%s",
            to_email,
            category,
            subject,
            self.host,
        )
        print(
            f"[EMAIL:SMTP] delivered to={to_email} subject={subject!r} category={category}",
            file=sys.stdout,
            flush=True,
        )


def build_email_service() -> EmailService:
    settings = get_settings()
    if settings.smtp_configured:
        logger.info("[EMAIL] SMTP transport active (%s:%s)", settings.smtp_host, settings.smtp_port)
        return SmtpEmailService(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_email=settings.smtp_from_email,
            use_tls=settings.smtp_use_tls,
        )
    logger.warning("[EMAIL] SMTP not configured — codes are printed to the console instead.")
    return MockEmailService()


email_service: EmailService = build_email_service()
