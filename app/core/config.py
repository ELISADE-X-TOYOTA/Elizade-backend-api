from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://elizade:elizade@localhost:5432/elizade_connect"
    jwt_secret: str = "dev-secret"
    jwt_expire_minutes: int = 10080  # 7 days
    admin_email: str = "divinewilson766@gmail.com"
    #: Refresh tokens outlive access tokens by design: the access token is
    #: the thing sent on every request, the refresh token only on renewal.
    refresh_token_expire_days: int = 60
    otp_expire_minutes: int = 10
    otp_length: int = 6

    # ── App Store / Play Store reviewer sign-in ──────────────────────────
    # One nominated account may sign in with a fixed code instead of an
    # emailed OTP, because review teams cannot receive one. Both must be set
    # or the bypass stays off, so a default build has no back door.
    #
    # This is a PERMANENT credential that is pasted into two third-party
    # consoles. Point it at a customer-role account holding demo data only,
    # use a long random string rather than 123456, and unset both once the
    # app is through review. See `domains/auth/review_bypass.py`.
    review_account_email: str = ""
    review_account_otp: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://elizade-web.vercel.app"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    #: The From address on every transactional email.
    #:
    #: The default WAS `noreply@meristemng.com` — the build vendor's domain,
    #: baked into the product as the fallback for any environment that forgot
    #: to set it. Customers saw "Meristem" on their Elizade sign-in codes, and
    #: nothing in the system considered that worth mentioning.
    #:
    #: elizade.NET, not .com — the company's site is elizade.net, and the
    #: earlier default here guessed the wrong TLD.
    #:
    #: Changing this is NOT enough on its own: the address has to be a verified
    #: sender in Postmark, with SPF and DKIM published for the domain, or mail
    #: stops going out entirely. `mail_sender_warning()` says so at boot rather
    #: than leaving it to a customer to notice.
    smtp_from_email: str = "noreply@elizade.net"
    smtp_use_tls: bool = True

    # Populate the database with demo content (30 vehicles, sample customers,
    # tickets, appointments) on boot. OFF by default: seeding is a development
    # convenience, and defaulting it on means the first production deploy
    # quietly fills the live database with fake Toyotas.
    seed_demo_data: bool = False

    # Postmark HTTP API. Preferred over SMTP: PaaS hosts commonly block
    # outbound 587, which shows up as a ~90s hang rather than a clean error.
    # Falls back to the SMTP password — Postmark uses one Server API Token for
    # both, so no extra value needs configuring.
    postmark_token: str = ""
    postmark_message_stream: str = "outbound"
    use_postmark_api: bool = True

    # DigitalOcean Spaces. Unset -> uploads stay on local disk.
    spaces_key: str = ""
    spaces_secret: str = ""
    spaces_bucket: str = ""
    spaces_region: str = "lon1"
    spaces_endpoint: str = "https://lon1.digitaloceanspaces.com"

    # Expo push. Unset -> notifications print to the console.
    push_enabled: bool = False
    expo_access_token: str = ""

    # SMS gateway (Termii). Unset -> messages print to the console.
    sms_api_key: str = ""
    sms_sender_id: str = "Elizade"
    sms_base_url: str = "https://api.ng.termii.com"

    # Shown in transactional email (footer / support links).
    #: OFFICIAL contact details, printed in the footer of every transactional
    #: email. These were placeholders: a `support@elizade.com` inbox and a
    #: 0700 service line that has no WhatsApp account behind it, on a domain
    #: (elizade.com) that is not the company's — the site is elizade.net.
    support_email: str = "info@elizade.net"
    support_phone: str = "09013248553"
    support_url: str = "https://www.elizade.net"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # Always allow the production admin portal, even if CORS_ORIGINS on the
        # host was set before this URL existed.
        for required in ("https://elizade-web.vercel.app",):
            if required not in origins:
                origins.append(required)
        return origins

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)

    @property
    def postmark_api_enabled(self) -> bool:
        token = self.postmark_token or self.smtp_password
        return bool(self.use_postmark_api and token and "postmark" in self.smtp_host.lower())

    @property
    def spaces_configured(self) -> bool:
        return bool(self.spaces_key and self.spaces_secret and self.spaces_bucket)

    @property
    def sms_configured(self) -> bool:
        return bool(self.sms_api_key and self.sms_sender_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
