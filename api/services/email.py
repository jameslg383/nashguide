"""Resend email delivery.

If settings.resend_override_to is set (useful while Resend domain verification
is pending — sandbox mode only allows sending to the account-owner address),
every outbound email is redirected to that address. The original intended
recipient is preserved as an X-Original-To header + in the subject line so
you can tell who each delivery was meant for.

To disable overriding once you've verified your domain at resend.com/domains,
unset RESEND_OVERRIDE_TO in .env and recreate the containers.
"""
import logging
import resend

from api.config import settings

log = logging.getLogger("email")
resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str, attachments: list[dict] | None = None) -> dict:
    actual_to = to
    headers = None
    effective_subject = subject

    override = (getattr(settings, "resend_override_to", "") or "").strip()
    if override and override.lower() != to.lower():
        log.info("Email override active — redirecting %s → %s", to, override)
        actual_to = override
        headers = {"X-Original-To": to}
        effective_subject = f"[→ {to}] {subject}"

    params = {
        "from": settings.RESEND_FROM,
        "to": [actual_to],
        "subject": effective_subject,
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments
    if headers:
        params["headers"] = headers
    return resend.Emails.send(params)
