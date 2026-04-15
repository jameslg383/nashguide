from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://nashguide:nashguide@localhost:5432/nashguide"
    REDIS_URL: str = "redis://localhost:6379/1"

    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MODE: str = "live"  # "live" | "sandbox"

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
    ADMIN_KEY: str = "dev-admin"
    SITE_URL: str = "http://localhost:8080"

    MARKETING_ENABLED: bool = True
    MARKETING_TWEETS_PER_DAY: int = 3
    MARKETING_BLOG_PER_WEEK: int = 1
    UPDATER_ENABLED: bool = True

    @property
    def paypal_base(self) -> str:
        return (
            "https://api-m.paypal.com"
            if self.PAYPAL_MODE == "live"
            else "https://api-m.sandbox.paypal.com"
        )


settings = Settings()
