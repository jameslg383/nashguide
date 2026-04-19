"""Delivery Agent — renders PDFs and sends delivery emails."""
import base64
import json
import logging
from pathlib import Path

import redis
from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.config import settings
from api.models.database import SessionLocal
from api.models.customer import Customer
from api.models.order import Order
from api.models.itinerary import Itinerary, EmailLog
from api.services.pdf_generator import render_itinerary_pdf
from api.services.email import send_email

log = logging.getLogger("delivery")
logging.basicConfig(level=logging.INFO)

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
QUEUE = "nashguide:jobs:delivery"

_email_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "api" / "templates")),
    autoescape=select_autoescape(["html"]),
)


def process_job(job: dict):
    db = SessionLocal()
    try:
        itin = db.get(Itinerary, job["itinerary_id"])
        if not itin:
            return
        order = db.get(Order, itin.order_id)
        customer = db.get(Customer, order.customer_id)

        # Render PDF
        pdf_rel = render_itinerary_pdf(itin.content_json, itin.public_slug)
        itin.pdf_url = f"{settings.site_url}{pdf_rel}"
        itin.status = "delivered"
        order.status = "delivered"
        db.commit()

        # Read PDF for attachment
        pdf_path = Path(__file__).resolve().parent.parent / pdf_rel.lstrip("/")
        pdf_bytes = pdf_path.read_bytes()

        tpl = _email_env.get_template("email_delivery.html")
        html = tpl.render(name=customer.name, trip_url=itin.web_url, pdf_url=itin.pdf_url)

        try:
            send_email(
                to=customer.email,
                subject="Your Nashville trip is ready 🎸",
                html=html,
                attachments=[{
                    "filename": f"NashGuide-{itin.public_slug}.pdf",
                    # Resend expects base64-encoded string for `content`. Passing a
                    # list of byte-ints works on some SDK versions but breaks Gmail's
                    # attachment preview in others.
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                    "content_type": "application/pdf",
                }],
            )
            status = "sent"
        except Exception as e:
            log.exception("Email send failed: %s", e)
            status = "failed"

        db.add(EmailLog(customer_id=customer.id, template="delivery", status=status))
        db.commit()
        log.info("Delivered itinerary %s to %s (%s)", itin.id, customer.email, status)
    except Exception as e:
        log.exception("Delivery failed: %s", e)
    finally:
        db.close()


def run():
    log.info("Delivery agent started, listening on %s", QUEUE)
    while True:
        item = _redis.blpop(QUEUE, timeout=5)
        if not item:
            continue
        _, payload = item
        try:
            process_job(json.loads(payload))
        except Exception:
            log.exception("Bad job: %s", payload)


if __name__ == "__main__":
    run()
