"""Social Scraper Agent — periodic Firecrawl-driven happy-hour ingestion.

Reads `scrape_sources` rows, fetches each via Firecrawl, runs the existing
LLM extraction, and drops findings into `user_submissions` (never live
tables) so a human approves them in the moderation queue.

Schedule:
- daily-frequency sources run every day at 03:30 CT.
- weekly-frequency sources run Sundays at 04:30 CT.
- manual-frequency sources only run when triggered from the admin UI.

The agent is fault-tolerant: any single source failure is logged, recorded
on the source row (`last_status`, `last_error`), and does not stop the loop.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterable

from apscheduler.schedulers.blocking import BlockingScheduler

from api.config import settings
from api.models import database as _db  # late binding so test-time monkeypatch of SessionLocal applies
from api.models.social import ScrapeSource, UserSubmission
from api.services import firecrawl_client, social_scraper

log = logging.getLogger("social_scraper_agent")
logging.basicConfig(level=logging.INFO)

# Tunables (kept in code rather than env — they're operational, not secret).
PER_SOURCE_DELAY_SEC = 4.0   # be polite to the upstream + Firecrawl quota.
MAX_SOURCES_PER_RUN = 50     # cap so a misbehaving cron can't exhaust quota.


def _scrape_one(source: ScrapeSource) -> dict:
    """Run the full pipeline for one source. Returns a small status dict."""
    body, fetcher = social_scraper.fetch_page(source.url)
    hint = None
    if source.source_type == "listing_page":
        hint = (
            "This is a roundup/listing page that may describe multiple "
            "Nashville venues. Return one entry per venue you can confirm; "
            "use the schema's `specials` array per venue. If unclear, omit."
        )
    extracted = social_scraper.extract_from_text(source.url, body, hint=hint)
    specials = extracted.get("specials") or []
    return {"fetcher": fetcher, "extracted": extracted, "specials_count": len(specials)}


def run_source(source_id: int) -> dict:
    """Run a single source by id. Used by the admin 'run now' button."""
    db = _db.SessionLocal()
    try:
        source = db.get(ScrapeSource, source_id)
        if not source:
            return {"ok": False, "error": "source not found"}
        return _run_and_persist(db, source)
    finally:
        db.close()


def _run_and_persist(db, source: ScrapeSource) -> dict:
    started = datetime.utcnow()
    try:
        result = _scrape_one(source)
    except Exception as e:  # noqa: BLE001 — agent must keep running on any failure
        log.exception("Scrape failed for source id=%s url=%s", source.id, source.url)
        source.last_scraped_at = started
        source.last_status = "error"
        source.last_error = str(e)[:1000]
        db.commit()
        return {"ok": False, "error": str(e), "source_id": source.id}

    sub = UserSubmission(
        submission_type="new_venue" if source.source_type == "venue_page" else "new_special",
        payload_json={
            "scraped": result["extracted"],
            "source_url": source.url,
            "source_id": source.id,
            "fetcher": result["fetcher"],
            "agent": "social_scraper_agent",
        },
        submitter_email=None,
        submitter_ip=f"agent:{result['fetcher']}",
        status="pending",
    )
    db.add(sub)

    source.last_scraped_at = started
    source.last_status = "ok"
    source.last_error = None
    source.last_specials_found = result["specials_count"]
    db.commit()

    log.info(
        "Scraped source id=%s url=%s specials=%d submission=%d",
        source.id, source.url, result["specials_count"], sub.id,
    )
    return {
        "ok": True,
        "source_id": source.id,
        "submission_id": sub.id,
        "specials": result["specials_count"],
        "fetcher": result["fetcher"],
    }


def _run_for_frequency(frequency: str) -> dict:
    """Run all active sources matching `frequency`."""
    if not settings.SOCIAL_SCRAPER_ENABLED:
        log.info("Social scraper disabled (SOCIAL_SCRAPER_ENABLED=false)")
        return {"ran": 0, "skipped": "disabled"}
    if not settings.ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — scraper will fail to extract")
        return {"ran": 0, "skipped": "no anthropic key"}

    db = _db.SessionLocal()
    ran = ok = errored = 0
    try:
        sources = (
            db.query(ScrapeSource)
            .filter(ScrapeSource.active.is_(True), ScrapeSource.frequency == frequency)
            .order_by(ScrapeSource.last_scraped_at.asc().nullsfirst())
            .limit(MAX_SOURCES_PER_RUN)
            .all()
        )
        log.info("Scraper sweep frequency=%s sources=%d firecrawl=%s",
                 frequency, len(sources), firecrawl_client.is_configured())
        for s in sources:
            result = _run_and_persist(db, s)
            ran += 1
            if result.get("ok"):
                ok += 1
            else:
                errored += 1
            time.sleep(PER_SOURCE_DELAY_SEC)
    finally:
        db.close()
    summary = {"frequency": frequency, "ran": ran, "ok": ok, "errored": errored}
    log.info("Scraper sweep done %s", summary)
    return summary


def daily_sweep():
    return _run_for_frequency("daily")


def weekly_sweep():
    return _run_for_frequency("weekly")


def run():
    sched = BlockingScheduler(timezone=settings.social_default_tz)
    sched.add_job(daily_sweep, "cron", hour=3, minute=30, id="social_daily")
    sched.add_job(weekly_sweep, "cron", day_of_week="sun", hour=4, minute=30, id="social_weekly")
    log.info("Social scraper agent started — firecrawl=%s",
             firecrawl_client.is_configured())
    sched.start()


if __name__ == "__main__":
    run()
