"""Planner Agent — consumes itinerary jobs from Redis and generates trip plans."""
import json
import logging
import secrets
import time

import redis

from api.config import settings
from api.models.database import SessionLocal
from api.models.order import Order, QuizResponse
from api.models.venue import Venue
from api.models.itinerary import Itinerary
from api.services import claude_ai

log = logging.getLogger("planner")
logging.basicConfig(level=logging.INFO)

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

QUEUE = "nashguide:jobs:itinerary"
DELIVERY_QUEUE = "nashguide:jobs:delivery"


def _venues_for_quiz(db, quiz: QuizResponse) -> list[dict]:
    q = db.query(Venue).filter(Venue.active == True)  # noqa: E712
    # Budget filter
    budget_cap = {"Budget-friendly": 2, "Mid-range": 3, "Splurge": 4, "Money's no object": 4}
    cap = budget_cap.get(quiz.budget, 4)
    q = q.filter(Venue.price_level <= cap)
    venues = q.all()
    return [
        {
            "id": v.id, "name": v.name, "address": v.address, "neighborhood": v.neighborhood,
            "category": v.category, "subcategory": v.subcategory, "price_level": v.price_level,
            "vibe_tags": v.vibe_tags, "best_time": v.best_time, "insider_tip": v.insider_tip,
        }
        for v in venues
    ]


def process_job(job: dict):
    db = SessionLocal()
    try:
        order = db.get(Order, job["order_id"])
        if not order or order.status != "paid":
            log.warning("Skipping job for order %s (status=%s)", job.get("order_id"), order and order.status)
            return
        quiz = db.query(QuizResponse).filter(QuizResponse.order_id == order.id).first()
        if not quiz:
            log.error("No quiz for order %s", order.id)
            return

        venues = _venues_for_quiz(db, quiz)
        log.info("Generating itinerary for order %s against %d venues", order.id, len(venues))

        content = claude_ai.generate_itinerary(quiz.raw_json, venues)

        slug = secrets.token_urlsafe(8)
        itin = Itinerary(
            order_id=order.id,
            quiz_response_id=quiz.id,
            public_slug=slug,
            content_json=content,
            status="generated",
            web_url=f"{settings.site_url}/trip/{slug}",
        )
        db.add(itin)
        db.commit()
        db.refresh(itin)

        _redis.rpush(DELIVERY_QUEUE, json.dumps({"itinerary_id": itin.id}))
        log.info("Itinerary %s generated for order %s", itin.id, order.id)
    except Exception as e:
        log.exception("Planner failed: %s", e)
    finally:
        db.close()


def run():
    log.info("Planner agent started, listening on %s", QUEUE)
    while True:
        item = _redis.blpop(QUEUE, timeout=5)
        if not item:
            continue
        _, payload = item
        try:
            process_job(json.loads(payload))
        except Exception:
            log.exception("Bad job payload: %s", payload)
            time.sleep(1)


if __name__ == "__main__":
    run()
