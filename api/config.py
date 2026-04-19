from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://nashguide:nashguide@localhost:5432/nashguide"
    REDIS_URL: str = "redis://localhost:6379/1"

    paypal_client_id: str = ""      # reads PAYPAL_CLIENT_ID env var
    paypal_client_secret: str = ""  # reads PAYPAL_CLIENT_SECRET env var
    paypal_mode: str = "live"       # "live" | "sandbox"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    RESEND_API_KEY: str = ""
    RESEND_FROM: str = "NashGuide AI <trips@nashguide.ai>"

    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_ACCESS_TOKEN: str = ""
    TWITTER_ACCESS_SECRET: str = ""

    GOOGLE_MAPS_API_KEY: str = ""

    SECRET_KEY: str = "dev-secret"
    admin_key: str = "dev-admin"  # reads ADMIN_KEY env var — legacy ?key= auth
    admin_user: str = "admin"     # session login username
    admin_pass: str = "admin"     # session login password
    site_url: str = "http://localhost:8080"  # reads SITE_URL env var

    MARKETING_ENABLED: bool = True
    MARKETING_TWEETS_PER_DAY: int = 3
    MARKETING_BLOG_PER_WEEK: int = 1
    UPDATER_ENABLED: bool = True

    @property
    def paypal_base(self) -> str:
        return (
            "https://api-m.paypal.com"
            if self.paypal_mode == "live"
            else "https://api-m.sandbox.paypal.com"
        )



settings = Settings()
