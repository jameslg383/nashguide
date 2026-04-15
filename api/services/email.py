"""Resend email delivery."""
import resend
from api.config import settings

resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str, attachments: list[dict] | None = None) -> dict:
    params = {
        "from": settings.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments
    return resend.Emails.send(params)
