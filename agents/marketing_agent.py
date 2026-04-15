"""Marketing Agent — generates tweets and blog posts on a schedule."""
import logging
import re
from datetime import datetime


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    return re.sub(r"[\s-]+", "-", text).strip("-")[:80]

from apscheduler.schedulers.blocking import BlockingScheduler

from api.config import settings
from api.models.database import SessionLocal
from api.models.content import BlogPost, SocialPost
from api.services import claude_ai

log = logging.getLogger("marketing")
logging.basicConfig(level=logging.INFO)


BLOG_TOPICS = [
    "The perfect 3-day Nashville itinerary in 2026",
    "Nashville bachelorette weekend: bar crawl + brunch guide",
    "Nashville with kids: 7 things that actually work",
    "Where to eat hot chicken in Nashville (ranked by a local)",
    "East Nashville vs. The Gulch vs. 12 South: which neighborhood is for you",
    "Honky-tonk survival guide: beyond Broadway",
    "Nashville on a budget: $100/day itinerary",
]


def generate_tweets_job():
    if not settings.MARKETING_ENABLED:
        return
    db = SessionLocal()
    try:
        tweets = claude_ai.generate_tweets(settings.MARKETING_TWEETS_PER_DAY)
        for t in tweets:
            db.add(SocialPost(platform="twitter", content=t, status="scheduled"))
        db.commit()
        log.info("Queued %d tweets", len(tweets))
    except Exception:
        log.exception("Tweet generation failed")
    finally:
        db.close()


def generate_blog_job():
    if not settings.MARKETING_ENABLED:
        return
    db = SessionLocal()
    try:
        existing_titles = {p.title for p in db.query(BlogPost).all()}
        topic = next((t for t in BLOG_TOPICS if t not in existing_titles), BLOG_TOPICS[0])
        post = claude_ai.generate_blog_post(topic)
        slug = post.get("slug") or slugify(post["title"])
        db.add(BlogPost(
            title=post["title"],
            slug=slug,
            content_md=post["content_md"],
            meta_description=post.get("meta_description"),
            keywords=post.get("keywords", []),
            status="published",
            published_at=datetime.utcnow(),
        ))
        db.commit()
        log.info("Published blog: %s", post["title"])
    except Exception:
        log.exception("Blog generation failed")
    finally:
        db.close()


def run():
    sched = BlockingScheduler()
    sched.add_job(generate_tweets_job, "cron", hour=9, id="tweets")
    sched.add_job(generate_blog_job, "cron", day_of_week="mon", hour=10, id="blog")
    log.info("Marketing agent started")
    sched.start()


if __name__ == "__main__":
    run()
