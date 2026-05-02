"""SQLAlchemy models for the /social vertical.

We keep array-shaped columns as JSON here so `Base.metadata.create_all` works
on both Postgres (prod) and SQLite (tests). The Alembic migration upgrades
those to true Postgres ARRAYs with GIN indexes in prod.
"""
from datetime import datetime, time, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.database import Base


VENUE_TYPES = (
    "bar",
    "restaurant",
    "hotel",
    "brewery",
    "rooftop",
    "dive",
    "cocktail_lounge",
    "music_venue",
)

VIBE_TAGS = (
    "live_music",
    "dog_friendly",
    "patio",
    "sports",
    "date_night",
    "dive",
    "upscale",
    "tourist_heavy",
    "local_favorite",
    "bachelorette_friendly",
    "bachelorette_avoid",
)

DEAL_TYPES = ("drink", "food", "both", "bogo", "flat_price", "percent_off")
SOURCE_TYPES = ("manual", "scraped", "user_submitted")
SUBMISSION_TYPES = ("new_venue", "new_special", "correction", "closed", "ad_inquiry")
SUBMISSION_STATUSES = ("pending", "approved", "rejected", "merged")
PLACEMENT_SLOTS = (
    "homepage_banner",
    "neighborhood_top",
    "venue_inline",
    "newsletter",
)


class SocialVenue(Base):
    __tablename__ = "social_venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    venue_type: Mapped[str] = mapped_column(String(32), index=True)
    neighborhood: Mapped[str] = mapped_column(String(96), index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(48), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_tier: Mapped[int] = mapped_column(Integer, default=2)
    vibe_tags: Mapped[list] = mapped_column(JSON, default=list)
    hours_json: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    specials: Mapped[list["HappyHourSpecial"]] = relationship(
        "HappyHourSpecial",
        back_populates="venue",
        cascade="all, delete-orphan",
    )


class HappyHourSpecial(Base):
    __tablename__ = "happy_hour_specials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(
        ForeignKey("social_venues.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    days_of_week: Mapped[list] = mapped_column(JSON, default=list)  # [0..6], Mon=0
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    deal_type: Mapped[str] = mapped_column(String(24), default="drink")
    discount_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dine_in_only: Mapped[bool] = mapped_column(Boolean, default=False)
    industry_only: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_membership: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    venue: Mapped[SocialVenue] = relationship("SocialVenue", back_populates="specials")


class ParkingSpot(Base):
    __tablename__ = "parking_spots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    parking_type: Mapped[str] = mapped_column(String(24), default="lot")
    nightly_rate: Mapped[str | None] = mapped_column(String(48), nullable=True)
    event_rate: Mapped[str | None] = mapped_column(String(48), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    near_neighborhood: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserSubmission(Base):
    __tablename__ = "user_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    submitter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitter_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(96), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


SCRAPE_SOURCE_TYPES = ("venue_page", "listing_page")
SCRAPE_FREQUENCIES = ("manual", "daily", "weekly")


class ScrapeSource(Base):
    """A URL the scraper agent should periodically visit.

    `venue_page` URLs are scraped 1:1 — output expected to describe one venue
    plus its specials. `listing_page` URLs are roundup articles ("best happy
    hours in Nashville right now") — the LLM will extract multiple venues.

    Every scrape, regardless of source, drops results into `user_submissions`
    for human approval. We never auto-write live data.
    """
    __tablename__ = "scrape_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_type: Mapped[str] = mapped_column(String(24), default="venue_page")
    frequency: Mapped[str] = mapped_column(String(16), default="weekly")
    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_venues.id", ondelete="SET NULL"), nullable=True
    )
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_specials_found: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdPlacement(Base):
    __tablename__ = "ad_placements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser_name: Mapped[str] = mapped_column(String(160))
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    placement_slot: Mapped[str] = mapped_column(String(48), index=True)
    target_neighborhood: Mapped[str | None] = mapped_column(String(96), nullable=True)
    target_vibe_tag: Mapped[str | None] = mapped_column(String(48), nullable=True)
    creative_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    click_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(160), nullable=True)
    subheadline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    monthly_rate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
