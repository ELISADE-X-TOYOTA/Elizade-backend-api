from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://elizade:elizade@localhost:5432/elizade_connect"
    jwt_secret: str = "dev-secret"
    jwt_expire_minutes: int = 10080  # 7 days
    admin_email: str = "divinewilson766@gmail.com"
    otp_expire_minutes: int = 10
    otp_length: int = 6
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://elizade-web.vercel.app"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@meristemng.com"
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
    support_email: str = "support@elizade.com"
    support_phone: str = "+234 700 354 9233"
    support_url: str = "https://elizade.com/contact"

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
