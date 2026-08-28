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
        # The code lives in `body`/`html_body`, neither of which the generic
        # notification print emits — so without this the dev console showed the
        # subject line and no way to actually sign in. Printed to stdout only,
        # never through `logger`, because logs commonly ship to an aggregator
        # and a one-time passcode has no business leaving the machine.
        #
        # Reachable only via MockEmailService, i.e. only when SMTP is
        # unconfigured. Configure SMTP and this transport is never constructed.
        print(
            f"\n{'=' * 58}\n"
            f"  OTP for {to_email}  ({purpose})\n"
            f"  CODE: {code}\n"
            f"{'=' * 58}\n",
            file=sys.stdout,
            flush=True,
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


class PostmarkApiEmailService(EmailService):
    """Postmark over HTTPS instead of SMTP.

    WHY THIS EXISTS: Railway — like most PaaS hosts — blocks outbound SMTP
    (25/465/587) to stop the platform being used to send spam. The symptom is
    not a clean refusal but a long hang: the connection sits until the socket
    timeout, so a registration request burned ~90s and then 502'd with
    "We couldn't send your verification code".

    The HTTP API uses port 443, which is never blocked, answers in a few
    seconds, and returns a specific error code instead of a timeout. Same
    Server API Token as the SMTP username/password.
    """

    ENDPOINT = "https://api.postmarkapp.com/email"

    def __init__(self, *, token: str, from_email: str, message_stream: str = "outbound") -> None:
        self.token = token
        self.from_email = from_email
        self.message_stream = message_stream

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
        import httpx  # noqa: PLC0415

        payload = {
            "From": formataddr(("Elizade Connect", self.from_email)),
            "To": to_email,
            "Subject": subject,
            "TextBody": body,
            "MessageStream": self.message_stream,
        }
        if html_body:
            payload["HtmlBody"] = html_body
        if category == "otp":
            # Postmark groups by tag in its Activity view, which makes an
            # "did the code go out?" question answerable in one click.
            payload["Tag"] = "otp"

        try:
            response = httpx.post(
                self.ENDPOINT,
                json=payload,
                headers={
                    "X-Postmark-Server-Token": self.token,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
        except httpx.HTTPError as exc:
            logger.exception("[EMAIL:POSTMARK] unreachable")
            raise EmailDeliveryError("Could not reach the email service.") from exc

        if response.status_code == 401:
            logger.error("[EMAIL:POSTMARK] server token rejected")
            raise EmailDeliveryError("Email service rejected our credentials.")
        if response.status_code >= 400:
            # Postmark returns an ErrorCode that says WHY — 406 inactive
            # recipient, 300 invalid address, 405 not allowed to send.
            try:
                detail = response.json()
                code = detail.get("ErrorCode")
                message = detail.get("Message", "")
            except Exception:  # noqa: BLE001
                code, message = response.status_code, response.text[:200]
            logger.error("[EMAIL:POSTMARK] rejected to=%s code=%s: %s", to_email, code, message)
            if code == 406:
                raise EmailDeliveryError("That address is suppressed — it previously bounced.")
            raise EmailDeliveryError("The email service rejected that message.")

        logger.info("[EMAIL:POSTMARK] delivered to=%s category=%s", to_email, category)
        print(
            f"[EMAIL:POSTMARK] delivered to={to_email} subject={subject!r} category={category}",
            file=sys.stdout,
            flush=True,
        )


def build_email_service() -> EmailService:
    settings = get_settings()

    # Preferred: the HTTP API. It works on hosts that block SMTP egress, which
    # is most PaaS platforms, and fails fast with a reason instead of hanging.
    if settings.postmark_api_enabled:
        logger.info("[EMAIL] Postmark HTTP transport active (from %s)", settings.smtp_from_email)
        return PostmarkApiEmailService(
            token=settings.postmark_token or settings.smtp_password,
            from_email=settings.smtp_from_email,
            message_stream=settings.postmark_message_stream,
        )

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
