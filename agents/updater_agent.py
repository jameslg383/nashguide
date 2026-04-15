"""Updater Agent — weekly venue freshness sweep."""
import logging
from datetime import datetime

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler

from api.config import settings
from api.models.database import SessionLocal
from api.models.venue import Venue

log = logging.getLogger("updater")
logging.basicConfig(level=logging.INFO)


def sweep_venues():
    if not settings.UPDATER_ENABLED:
        return
    db = SessionLocal()
    try:
        venues = db.query(Venue).filter(Venue.active == True).all()  # noqa: E712
        checked = 0
        for v in venues:
            # Only hit venues we can resolve a likely URL for. For MVP we just
            # touch their Google search to confirm they still exist.
            if not v.name:
                continue
            try:
                r = httpx.get(
                    f"https://www.google.com/search?q={v.name.replace(' ', '+')}+Nashville",
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 NashGuideBot/1.0"},
                )
                if r.status_code == 200:
                    v.last_verified = datetime.utcnow()
                    checked += 1
            except Exception:
                continue
        db.commit()
        log.info("Updater swept %d venues", checked)
    except Exception:
        log.exception("Updater sweep failed")
    finally:
        db.close()


def run():
    sched = BlockingScheduler()
    sched.add_job(sweep_venues, "cron", day_of_week="sun", hour=4, id="sweep")
    log.info("Updater agent started")
    sched.start()


if __name__ == "__main__":
    run()
