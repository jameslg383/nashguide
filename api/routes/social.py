"""The /social vertical: Nashville happy hours, drink/food specials, venue
profiles, parking, ad placements, user submissions, admin moderation.

Public routes are anonymous. Admin routes are gated by ?key=NASHGUIDE_ADMIN_KEY
(matching the existing ?key= pattern used by api/routes/admin.py).

"Happy right now" is computed server-side in America/Chicago.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 fallback
    ZoneInfo = None  # type: ignore

from api.config import settings
from api.models.database import get_db
from api.models.social import (
    AdPlacement,
    HappyHourSpecial,
    ParkingSpot,
    SocialVenue,
    UserSubmission,
    VENUE_TYPES,
    VIBE_TAGS,
)

log = logging.getLogger("social")

router = APIRouter(tags=["social"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

NEIGHBORHOODS = (
    "Broadway",
    "The Gulch",
    "Germantown",
    "East Nashville",
    "12 South",
    "Midtown",
    "Wedgewood-Houston",
    "Berry Hill",
    "Donelson",
    "Sylvan Park",
    "Downtown",
    "Music Row",
    "Hillsboro Village",
    "SoBro",
)

DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_LABELS_FULL = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text or "venue"


def _admin_key() -> str:
    """Effective admin key: prefer NASHGUIDE_ADMIN_KEY, fall back to ADMIN_KEY.

    Re-reads from env on every call so tests can monkeypatch the env var
    without rebuilding the Settings singleton.
    """
    import os as _os
    return (
        _os.environ.get("NASHGUIDE_ADMIN_KEY")
        or settings.nashguide_admin_key
        or _os.environ.get("ADMIN_KEY")
        or settings.admin_key
    )


def require_social_admin(key: str = Query("", description="admin key")) -> bool:
    if not key or key != _admin_key():
        raise HTTPException(401, "Invalid admin key")
    return True


def _now_local() -> datetime:
    """Server-time normalized to America/Chicago."""
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(settings.social_default_tz))


def _today_dow() -> int:
    """0..6 Mon..Sun in local time."""
    return _now_local().weekday()


def _is_special_active(s: HappyHourSpecial, ref: datetime | None = None) -> bool:
    """Is this special running at `ref` (defaults to now)?"""
    if not s.active:
        return False
    ref = ref or _now_local()
    naive_ref = ref.replace(tzinfo=None) if ref.tzinfo else ref
    today = naive_ref.date()
    if s.effective_from and today < s.effective_from:
        return False
    if s.effective_until and today > s.effective_until:
        return False
    dow = naive_ref.weekday()
    days = list(s.days_of_week or [])
    if days and dow not in days:
        return False
    if s.start_time and s.end_time:
        t = naive_ref.time()
        if s.start_time <= s.end_time:
            return s.start_time <= t <= s.end_time
        # overnight (e.g. 22:00 → 02:00)
        return t >= s.start_time or t <= s.end_time
    return True


def _ends_in_minutes(s: HappyHourSpecial, ref: datetime | None = None) -> int | None:
    if not s.end_time:
        return None
    ref = ref or _now_local()
    naive = ref.replace(tzinfo=None) if ref.tzinfo else ref
    end = datetime.combine(naive.date(), s.end_time)
    if s.start_time and s.end_time and s.start_time > s.end_time and naive.time() <= s.end_time:
        # overnight, we're already in the next-day window — end is today
        pass
    elif s.start_time and s.end_time and s.start_time > s.end_time:
        end = end + timedelta(days=1)
    delta = (end - naive).total_seconds() / 60
    return int(delta) if delta >= 0 else None


def _venue_open_now(v: SocialVenue, ref: datetime | None = None) -> bool:
    hours = v.hours_json or {}
    if not hours:
        return True  # unknown — don't filter out
    ref = ref or _now_local()
    naive = ref.replace(tzinfo=None) if ref.tzinfo else ref
    key = DAY_LABELS_FULL[naive.weekday()].lower()
    today = hours.get(key) or hours.get(key[:3])
    if not today:
        return False
    open_s, close_s = (today.get("open"), today.get("close")) if isinstance(today, dict) else (None, None)
    if not open_s or not close_s:
        return True
    try:
        open_t = time.fromisoformat(open_s)
        close_t = time.fromisoformat(close_s)
    except ValueError:
        return True
    t = naive.time()
    if open_t <= close_t:
        return open_t <= t <= close_t
    return t >= open_t or t <= close_t


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _serialize_venue(v: SocialVenue) -> dict[str, Any]:
    return {
        "id": v.id,
        "slug": v.slug,
        "name": v.name,
        "venue_type": v.venue_type,
        "neighborhood": v.neighborhood,
        "address": v.address,
        "lat": v.lat,
        "lng": v.lng,
        "phone": v.phone,
        "website": v.website,
        "instagram": v.instagram,
        "price_tier": v.price_tier,
        "vibe_tags": v.vibe_tags or [],
        "hours_json": v.hours_json or {},
        "description": v.description,
        "featured": v.featured,
        "verified": v.verified,
    }


def _serialize_special(s: HappyHourSpecial, include_venue: bool = False) -> dict[str, Any]:
    out = {
        "id": s.id,
        "venue_id": s.venue_id,
        "title": s.title,
        "description": s.description,
        "days_of_week": s.days_of_week or [],
        "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
        "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
        "deal_type": s.deal_type,
        "discount_value": s.discount_value,
        "active_now": _is_special_active(s),
        "ends_in_min": _ends_in_minutes(s),
    }
    if include_venue and s.venue is not None:
        out["venue"] = {"slug": s.venue.slug, "name": s.venue.name, "neighborhood": s.venue.neighborhood}
    return out


def _format_time_label(t: time | None) -> str:
    if not t:
        return ""
    return t.strftime("%-I:%M %p").lstrip("0") if hasattr(t, "strftime") else str(t)


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-IP). Redis-backed elsewhere; this keeps
# tests hermetic and is fine for a low-volume submit form.
# ---------------------------------------------------------------------------

_RATE_BUCKET: dict[str, list[float]] = {}
_RATE_WINDOW_SECONDS = 3600
_RATE_MAX = 5


def _rate_limit_check(ip: str) -> None:
    now = _time.monotonic()
    bucket = _RATE_BUCKET.setdefault(ip, [])
    cutoff = now - _RATE_WINDOW_SECONDS
    bucket[:] = [t for t in bucket if t >= cutoff]
    if len(bucket) >= _RATE_MAX:
        raise HTTPException(429, "Too many submissions — try again in an hour")
    bucket.append(now)


def _reset_rate_limit() -> None:
    """Test hook."""
    _RATE_BUCKET.clear()


# ---------------------------------------------------------------------------
# Ad rendering helper
# ---------------------------------------------------------------------------


def _pick_ad(
    db: Session,
    slot: str,
    *,
    neighborhood: str | None = None,
    vibe: str | None = None,
) -> AdPlacement | None:
    now = datetime.utcnow()
    q = db.query(AdPlacement).filter(
        AdPlacement.placement_slot == slot, AdPlacement.active.is_(True)
    )
    q = q.filter(or_(AdPlacement.starts_at.is_(None), AdPlacement.starts_at <= now))
    q = q.filter(or_(AdPlacement.ends_at.is_(None), AdPlacement.ends_at >= now))
    if neighborhood:
        q = q.filter(
            or_(
                AdPlacement.target_neighborhood.is_(None),
                AdPlacement.target_neighborhood == neighborhood,
            )
        )
    if vibe:
        q = q.filter(
            or_(
                AdPlacement.target_vibe_tag.is_(None),
                AdPlacement.target_vibe_tag == vibe,
            )
        )
    ad = q.order_by(func.random()).first()
    if ad:
        ad.impressions += 1
        db.commit()
    return ad


# ===========================================================================
# Public routes
# ===========================================================================


@router.get("/social", response_class=HTMLResponse)
def social_landing(request: Request, db: Session = Depends(get_db)):
    now = _now_local()
    dow = now.weekday()

    active_specials = (
        db.query(HappyHourSpecial)
        .options(selectinload(HappyHourSpecial.venue))
        .filter(HappyHourSpecial.active.is_(True))
        .all()
    )
    happy_now = [s for s in active_specials if _is_special_active(s, now)]
    happy_now.sort(key=lambda s: (_ends_in_minutes(s) or 9999))

    featured_venues = (
        db.query(SocialVenue)
        .filter(SocialVenue.active.is_(True), SocialVenue.featured.is_(True))
        .limit(8)
        .all()
    )

    neighborhood_counts = dict(
        db.query(SocialVenue.neighborhood, func.count(SocialVenue.id))
        .filter(SocialVenue.active.is_(True))
        .group_by(SocialVenue.neighborhood)
        .all()
    )

    ad = _pick_ad(db, "homepage_banner")

    return templates.TemplateResponse(
        "social/landing.html",
        {
            "request": request,
            "now": now,
            "day_label": DAY_LABELS_FULL[dow],
            "happy_now": happy_now[:6],
            "happy_now_count": len(happy_now),
            "featured_venues": featured_venues,
            "neighborhoods": [
                (n, neighborhood_counts.get(n, 0)) for n in NEIGHBORHOODS
            ],
            "vibe_tags": VIBE_TAGS,
            "ad": ad,
            "format_time": _format_time_label,
            "ends_in_min": _ends_in_minutes,
            "slugify": _slugify,
        },
    )


@router.get("/social/now")
def social_now_json(db: Session = Depends(get_db)):
    """JSON: all specials active this exact moment (America/Chicago)."""
    now = _now_local()
    rows = (
        db.query(HappyHourSpecial)
        .options(selectinload(HappyHourSpecial.venue))
        .filter(HappyHourSpecial.active.is_(True))
        .all()
    )
    happy = [_serialize_special(s, include_venue=True) for s in rows if _is_special_active(s, now)]
    happy.sort(key=lambda s: s["ends_in_min"] if s["ends_in_min"] is not None else 9999)
    return {
        "as_of": now.isoformat(),
        "tz": settings.social_default_tz,
        "count": len(happy),
        "specials": happy,
    }


@router.get("/social/venues", response_class=HTMLResponse)
def social_venues_list(
    request: Request,
    db: Session = Depends(get_db),
    neighborhood: str | None = None,
    vibe: str | None = None,
    type: str | None = Query(None, alias="type"),
    has_happy_hour: bool = False,
    open_now: bool = False,
    q: str | None = None,
    page: int = 1,
    page_size: int = 24,
):
    page = max(page, 1)
    page_size = min(max(page_size, 6), 60)
    query = db.query(SocialVenue).filter(SocialVenue.active.is_(True))
    if neighborhood:
        query = query.filter(SocialVenue.neighborhood == neighborhood)
    if type:
        query = query.filter(SocialVenue.venue_type == type)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(SocialVenue.name).like(like),
                func.lower(func.coalesce(SocialVenue.description, "")).like(like),
            )
        )
    venues = query.order_by(SocialVenue.featured.desc(), SocialVenue.name.asc()).all()

    if vibe:
        venues = [v for v in venues if vibe in (v.vibe_tags or [])]
    if has_happy_hour:
        ids_with = {
            row[0]
            for row in db.query(HappyHourSpecial.venue_id)
            .filter(HappyHourSpecial.active.is_(True))
            .distinct()
            .all()
        }
        venues = [v for v in venues if v.id in ids_with]
    if open_now:
        venues = [v for v in venues if _venue_open_now(v)]

    total = len(venues)
    start = (page - 1) * page_size
    paginated = venues[start : start + page_size]

    return templates.TemplateResponse(
        "social/venues_list.html",
        {
            "request": request,
            "venues": paginated,
            "neighborhoods": NEIGHBORHOODS,
            "venue_types": VENUE_TYPES,
            "vibe_tags": VIBE_TAGS,
            "filters": {
                "neighborhood": neighborhood,
                "vibe": vibe,
                "type": type,
                "has_happy_hour": has_happy_hour,
                "open_now": open_now,
                "q": q,
            },
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_next": start + page_size < total,
            "has_prev": page > 1,
            "slugify": _slugify,
        },
    )


@router.get("/social/venues/{slug}", response_class=HTMLResponse)
def social_venue_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    venue = (
        db.query(SocialVenue)
        .options(selectinload(SocialVenue.specials))
        .filter(SocialVenue.slug == slug, SocialVenue.active.is_(True))
        .first()
    )
    if not venue:
        raise HTTPException(404, "Venue not found")

    now = _now_local()
    dow = now.weekday()
    specials_active = [s for s in venue.specials if s.active]
    today_specials = [s for s in specials_active if not s.days_of_week or dow in (s.days_of_week or [])]

    by_day: dict[int, list[HappyHourSpecial]] = {i: [] for i in range(7)}
    for s in specials_active:
        days = s.days_of_week or list(range(7))
        for d in days:
            if 0 <= d <= 6:
                by_day[d].append(s)

    days_since_verify = None
    if venue.last_verified_at:
        delta = datetime.utcnow() - venue.last_verified_at
        days_since_verify = delta.days

    ad = _pick_ad(db, "venue_inline", neighborhood=venue.neighborhood)

    jsonld = _venue_jsonld(venue)

    return templates.TemplateResponse(
        "social/venue_detail.html",
        {
            "request": request,
            "venue": venue,
            "now": now,
            "today_specials": today_specials,
            "by_day": by_day,
            "day_labels": DAY_LABELS_FULL,
            "days_since_verify": days_since_verify,
            "ad": ad,
            "format_time": _format_time_label,
            "is_active": _is_special_active,
            "ends_in_min": _ends_in_minutes,
            "jsonld": jsonld,
            "site_url": settings.site_url.rstrip("/"),
        },
    )


@router.get("/social/neighborhoods/{slug}", response_class=HTMLResponse)
def social_neighborhood(slug: str, request: Request, db: Session = Depends(get_db)):
    name = next((n for n in NEIGHBORHOODS if _slugify(n) == slug), None)
    if not name:
        raise HTTPException(404, "Neighborhood not found")

    venues = (
        db.query(SocialVenue)
        .options(selectinload(SocialVenue.specials))
        .filter(SocialVenue.neighborhood == name, SocialVenue.active.is_(True))
        .all()
    )
    now = _now_local()

    def venue_score(v: SocialVenue) -> int:
        return sum(1 for s in v.specials if s.active and _is_special_active(s, now))

    venues.sort(key=lambda v: (-venue_score(v), v.name))
    ad = _pick_ad(db, "neighborhood_top", neighborhood=name)

    return templates.TemplateResponse(
        "social/neighborhood.html",
        {
            "request": request,
            "neighborhood": name,
            "venues": venues,
            "happy_now": [
                s
                for v in venues
                for s in v.specials
                if s.active and _is_special_active(s, now)
            ],
            "ad": ad,
            "format_time": _format_time_label,
            "is_active": _is_special_active,
            "ends_in_min": _ends_in_minutes,
        },
    )


@router.get("/social/happy-hours", response_class=HTMLResponse)
def social_happy_hours_master(
    request: Request,
    db: Session = Depends(get_db),
    day: int | None = None,
    neighborhood: str | None = None,
):
    if day is None:
        day = _today_dow()
    day = max(0, min(day, 6))

    rows = (
        db.query(HappyHourSpecial)
        .options(selectinload(HappyHourSpecial.venue))
        .filter(HappyHourSpecial.active.is_(True))
        .all()
    )
    rows = [s for s in rows if not s.days_of_week or day in (s.days_of_week or [])]
    if neighborhood:
        rows = [s for s in rows if s.venue and s.venue.neighborhood == neighborhood]

    def slot_of(s: HappyHourSpecial) -> str:
        if not s.start_time:
            return "All day"
        h = s.start_time.hour
        if h < 12:
            return "Morning / Brunch"
        if h < 16:
            return "Afternoon (12–4 PM)"
        if h < 19:
            return "Happy Hour (4–7 PM)"
        if h < 22:
            return "Evening (7–10 PM)"
        return "Late Night (10 PM+)"

    grouped: dict[str, list[HappyHourSpecial]] = {}
    for s in rows:
        grouped.setdefault(slot_of(s), []).append(s)
    for slot in grouped:
        grouped[slot].sort(key=lambda s: (s.start_time or time(0, 0)))

    slot_order = [
        "Morning / Brunch",
        "Afternoon (12–4 PM)",
        "Happy Hour (4–7 PM)",
        "Evening (7–10 PM)",
        "Late Night (10 PM+)",
        "All day",
    ]
    grouped_sorted = [(s, grouped[s]) for s in slot_order if s in grouped]

    return templates.TemplateResponse(
        "social/happy_hours.html",
        {
            "request": request,
            "day": day,
            "day_labels": DAY_LABELS,
            "day_labels_full": DAY_LABELS_FULL,
            "neighborhoods": NEIGHBORHOODS,
            "neighborhood": neighborhood,
            "grouped": grouped_sorted,
            "format_time": _format_time_label,
            "total": sum(len(v) for _, v in grouped_sorted),
        },
    )


@router.get("/social/parking", response_class=HTMLResponse)
def social_parking(
    request: Request, db: Session = Depends(get_db), near: str | None = None
):
    q = db.query(ParkingSpot).filter(ParkingSpot.active.is_(True))
    if near:
        q = q.filter(ParkingSpot.near_neighborhood == near)
    spots = q.order_by(ParkingSpot.near_neighborhood, ParkingSpot.name).all()
    return templates.TemplateResponse(
        "social/parking.html",
        {
            "request": request,
            "spots": spots,
            "near": near,
            "neighborhoods": NEIGHBORHOODS,
        },
    )


@router.get("/social/submit", response_class=HTMLResponse)
def social_submit_form(request: Request):
    return templates.TemplateResponse(
        "social/submit.html",
        {
            "request": request,
            "neighborhoods": NEIGHBORHOODS,
            "venue_types": VENUE_TYPES,
            "loaded_at": int(_time.time()),
        },
    )


@router.post("/social/submit", response_class=HTMLResponse)
async def social_submit_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    submission_type = (form.get("submission_type") or "").strip()
    if submission_type not in ("new_venue", "new_special", "correction", "closed"):
        raise HTTPException(400, "Invalid submission_type")

    # Honeypot — real users don't see this field, bots fill it.
    if (form.get("website_url") or "").strip():
        log.info("Honeypot tripped from ip=%s", _client_ip(request))
        return templates.TemplateResponse(
            "social/submit_thanks.html", {"request": request}
        )

    # Min-time-on-page (>2 seconds). Bots usually post sub-second.
    try:
        loaded_at = int(form.get("loaded_at") or "0")
        if loaded_at and (int(_time.time()) - loaded_at) < 2:
            log.info("Submit too fast from ip=%s (delta<2s)", _client_ip(request))
            return templates.TemplateResponse(
                "social/submit_thanks.html", {"request": request}
            )
    except ValueError:
        pass

    ip = _client_ip(request)
    _rate_limit_check(ip)

    payload = {k: v for k, v in form.items() if k not in {"website_url", "loaded_at"}}
    sub = UserSubmission(
        submission_type=submission_type,
        payload_json=payload,
        submitter_email=(form.get("submitter_email") or None),
        submitter_ip=ip,
        status="pending",
    )
    db.add(sub)
    db.commit()
    log.info("Submission saved id=%s type=%s ip=%s", sub.id, submission_type, ip)
    return templates.TemplateResponse(
        "social/submit_thanks.html", {"request": request, "submission_id": sub.id}
    )


@router.get("/social/advertise", response_class=HTMLResponse)
def social_advertise(request: Request):
    return templates.TemplateResponse(
        "social/advertise.html",
        {
            "request": request,
            "packages": [
                {"name": "Neighborhood Spotlight", "price": 99, "slot": "neighborhood_top"},
                {"name": "Vibe Targeting", "price": 149, "slot": "venue_inline"},
                {"name": "Homepage Banner", "price": 299, "slot": "homepage_banner"},
            ],
        },
    )


@router.post("/social/advertise")
async def social_advertise_inquiry(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    ip = _client_ip(request)
    if (form.get("website_url") or "").strip():
        return RedirectResponse("/social/advertise?ok=1", status_code=303)
    _rate_limit_check(ip)
    sub = UserSubmission(
        submission_type="ad_inquiry",
        payload_json={k: v for k, v in form.items() if k != "website_url"},
        submitter_email=form.get("contact_email"),
        submitter_ip=ip,
        status="pending",
    )
    db.add(sub)
    db.commit()
    return RedirectResponse("/social/advertise?ok=1", status_code=303)


@router.get("/social/ad/{ad_id}/click")
def social_ad_click(ad_id: int, db: Session = Depends(get_db)):
    ad = db.get(AdPlacement, ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    ad.clicks += 1
    db.commit()
    target = ad.click_url or "/social"
    return RedirectResponse(target, status_code=302)


# ---------------------------------------------------------------------------
# SEO: sitemap + JSON-LD helpers
# ---------------------------------------------------------------------------


def _venue_jsonld(v: SocialVenue) -> dict[str, Any]:
    site = settings.site_url.rstrip("/")
    schema_type = "FoodEstablishment" if v.venue_type in ("restaurant", "brewery") else "LocalBusiness"
    out: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": v.name,
        "url": f"{site}/social/venues/{v.slug}",
        "priceRange": "$" * (v.price_tier or 2),
    }
    if v.address:
        out["address"] = {"@type": "PostalAddress", "streetAddress": v.address, "addressLocality": "Nashville", "addressRegion": "TN"}
    if v.lat and v.lng:
        out["geo"] = {"@type": "GeoCoordinates", "latitude": v.lat, "longitude": v.lng}
    if v.phone:
        out["telephone"] = v.phone
    return out


@router.get("/social/sitemap.xml", response_class=PlainTextResponse)
def social_sitemap(db: Session = Depends(get_db)):
    site = settings.site_url.rstrip("/")
    urls = [f"{site}/social", f"{site}/social/happy-hours", f"{site}/social/parking", f"{site}/social/advertise"]
    for n in NEIGHBORHOODS:
        urls.append(f"{site}/social/neighborhoods/{_slugify(n)}")
    venues = db.query(SocialVenue.slug).filter(SocialVenue.active.is_(True)).all()
    for (slug,) in venues:
        urls.append(f"{site}/social/venues/{slug}")
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append(f"<url><loc>{u}</loc></url>")
    body.append("</urlset>")
    return PlainTextResponse("\n".join(body), media_type="application/xml")


# ===========================================================================
# Admin routes (?key=NASHGUIDE_ADMIN_KEY)
# ===========================================================================


@router.get("/admin/social", response_class=HTMLResponse)
def admin_social_home(_: bool = Depends(require_social_admin), db: Session = Depends(get_db)):
    counts = {
        "venues": db.query(func.count(SocialVenue.id)).scalar() or 0,
        "specials": db.query(func.count(HappyHourSpecial.id)).scalar() or 0,
        "submissions_pending": db.query(func.count(UserSubmission.id))
        .filter(UserSubmission.status == "pending")
        .scalar()
        or 0,
        "ads_active": db.query(func.count(AdPlacement.id))
        .filter(AdPlacement.active.is_(True))
        .scalar()
        or 0,
    }
    k = _admin_key()
    return HTMLResponse(
        f"""<!doctype html><html><body style='font-family:system-ui;max-width:720px;margin:40px auto'>
        <h1>NashGuide Social — Admin</h1>
        <ul>
          <li>Venues: <b>{counts['venues']}</b></li>
          <li>Specials: <b>{counts['specials']}</b></li>
          <li>Pending submissions: <b>{counts['submissions_pending']}</b></li>
          <li>Active ads: <b>{counts['ads_active']}</b></li>
        </ul>
        <p>
          <a href='/admin/social/venues?key={k}'>Venues</a> ·
          <a href='/admin/social/specials?key={k}'>Specials</a> ·
          <a href='/admin/social/submissions?key={k}'>Submissions</a> ·
          <a href='/admin/social/ads?key={k}'>Ads</a> ·
          <a href='/admin/social/scrape?key={k}'>Scrape URL</a>
        </p>
        </body></html>"""
    )


@router.get("/admin/social/submissions", response_class=HTMLResponse)
def admin_submissions(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
    status: str = "pending",
):
    rows = (
        db.query(UserSubmission)
        .filter(UserSubmission.status == status)
        .order_by(UserSubmission.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin_social/submissions.html",
        {
            "request": request,
            "rows": rows,
            "status": status,
            "key": _admin_key(),
        },
    )


@router.post("/admin/social/submissions/{sub_id}/approve")
def admin_submission_approve(
    sub_id: int,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    sub = db.get(UserSubmission, sub_id)
    if not sub:
        raise HTTPException(404, "Not found")
    payload = sub.payload_json or {}

    if sub.submission_type == "new_venue":
        slug = _slugify(payload.get("name") or f"venue-{sub.id}")
        venue = SocialVenue(
            slug=slug,
            name=payload.get("name") or slug,
            venue_type=payload.get("venue_type") or "bar",
            neighborhood=payload.get("neighborhood") or "Downtown",
            address=payload.get("address"),
            description=payload.get("description"),
            website=payload.get("website"),
            verified=False,
            active=True,
        )
        db.add(venue)
        db.flush()

    elif sub.submission_type == "new_special":
        venue_slug = payload.get("venue_slug")
        venue = db.query(SocialVenue).filter(SocialVenue.slug == venue_slug).first()
        if not venue:
            raise HTTPException(400, "Specify an existing venue_slug to attach this special")
        days = payload.get("days_of_week") or ""
        if isinstance(days, str):
            try:
                days_list = [int(d) for d in days.split(",") if d.strip()]
            except ValueError:
                days_list = []
        else:
            days_list = list(days)
        special = HappyHourSpecial(
            venue_id=venue.id,
            title=payload.get("title") or "Happy hour",
            description=payload.get("description"),
            days_of_week=days_list,
            start_time=_parse_time(payload.get("start_time")),
            end_time=_parse_time(payload.get("end_time")),
            deal_type=payload.get("deal_type") or "drink",
            discount_value=payload.get("discount_value"),
            source="user_submitted",
            active=True,
        )
        db.add(special)

    elif sub.submission_type == "closed":
        venue = db.query(SocialVenue).filter(SocialVenue.slug == payload.get("venue_slug")).first()
        if venue:
            venue.active = False

    sub.status = "approved"
    sub.reviewed_at = datetime.utcnow()
    sub.reviewed_by = "admin"
    db.commit()
    return RedirectResponse(f"/admin/social/submissions?key={_admin_key()}", status_code=303)


@router.post("/admin/social/submissions/{sub_id}/reject")
async def admin_submission_reject(
    sub_id: int,
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    sub = db.get(UserSubmission, sub_id)
    if not sub:
        raise HTTPException(404, "Not found")
    form = await request.form()
    sub.status = "rejected"
    sub.review_notes = form.get("notes")
    sub.reviewed_at = datetime.utcnow()
    sub.reviewed_by = "admin"
    db.commit()
    return RedirectResponse(f"/admin/social/submissions?key={_admin_key()}", status_code=303)


@router.get("/admin/social/venues", response_class=HTMLResponse)
def admin_venues(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    venues = db.query(SocialVenue).order_by(SocialVenue.neighborhood, SocialVenue.name).all()
    return templates.TemplateResponse(
        "admin_social/venues.html",
        {"request": request, "venues": venues, "key": _admin_key()},
    )


@router.post("/admin/social/venues/{venue_id}/verify")
def admin_venue_verify(
    venue_id: int,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    v = db.get(SocialVenue, venue_id)
    if not v:
        raise HTTPException(404, "Not found")
    v.verified = True
    v.last_verified_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/admin/social/venues?key={_admin_key()}", status_code=303)


@router.post("/admin/social/venues/{venue_id}/toggle")
def admin_venue_toggle(
    venue_id: int,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    v = db.get(SocialVenue, venue_id)
    if not v:
        raise HTTPException(404, "Not found")
    v.active = not v.active
    db.commit()
    return RedirectResponse(f"/admin/social/venues?key={_admin_key()}", status_code=303)


@router.get("/admin/social/specials", response_class=HTMLResponse)
def admin_specials(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    specials = (
        db.query(HappyHourSpecial)
        .options(selectinload(HappyHourSpecial.venue))
        .order_by(HappyHourSpecial.created_at.desc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse(
        "admin_social/specials.html",
        {
            "request": request,
            "specials": specials,
            "format_time": _format_time_label,
            "key": _admin_key(),
        },
    )


@router.post("/admin/social/specials/bulk-deactivate-stale")
def admin_specials_bulk_deactivate(
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=90)
    stale = (
        db.query(HappyHourSpecial)
        .filter(
            HappyHourSpecial.active.is_(True),
            or_(
                HappyHourSpecial.last_verified_at.is_(None),
                HappyHourSpecial.last_verified_at < cutoff,
            ),
            HappyHourSpecial.created_at < cutoff,
        )
        .all()
    )
    for s in stale:
        s.active = False
    db.commit()
    return RedirectResponse(
        f"/admin/social/specials?key={_admin_key()}&deactivated={len(stale)}", status_code=303
    )


@router.get("/admin/social/ads", response_class=HTMLResponse)
def admin_ads(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    ads = db.query(AdPlacement).order_by(AdPlacement.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin_social/ads.html",
        {"request": request, "ads": ads, "slots": ["homepage_banner", "neighborhood_top", "venue_inline", "newsletter"], "key": _admin_key()},
    )


@router.post("/admin/social/ads")
async def admin_ad_create(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    ad = AdPlacement(
        advertiser_name=form.get("advertiser_name") or "Anonymous",
        contact_email=form.get("contact_email"),
        placement_slot=form.get("placement_slot") or "homepage_banner",
        target_neighborhood=form.get("target_neighborhood") or None,
        target_vibe_tag=form.get("target_vibe_tag") or None,
        creative_url=form.get("creative_url"),
        click_url=form.get("click_url"),
        headline=form.get("headline"),
        subheadline=form.get("subheadline"),
        monthly_rate_cents=int(form.get("monthly_rate_cents") or 0) or None,
        active=True,
    )
    db.add(ad)
    db.commit()
    return RedirectResponse(f"/admin/social/ads?key={_admin_key()}", status_code=303)


@router.post("/admin/social/ads/{ad_id}/toggle")
def admin_ad_toggle(
    ad_id: int,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    ad = db.get(AdPlacement, ad_id)
    if not ad:
        raise HTTPException(404, "Not found")
    ad.active = not ad.active
    db.commit()
    return RedirectResponse(f"/admin/social/ads?key={_admin_key()}", status_code=303)


@router.get("/admin/social/ads/export")
def admin_ads_export(
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "id", "advertiser_name", "placement_slot", "target_neighborhood",
        "target_vibe_tag", "active", "impressions", "clicks", "ctr_pct",
        "monthly_rate_cents", "starts_at", "ends_at",
    ])
    for ad in db.query(AdPlacement).all():
        ctr = (ad.clicks / ad.impressions * 100) if ad.impressions else 0
        w.writerow([
            ad.id, ad.advertiser_name, ad.placement_slot, ad.target_neighborhood or "",
            ad.target_vibe_tag or "", ad.active, ad.impressions, ad.clicks, f"{ctr:.2f}",
            ad.monthly_rate_cents or "",
            ad.starts_at.isoformat() if ad.starts_at else "",
            ad.ends_at.isoformat() if ad.ends_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=social_ads.csv"},
    )


@router.get("/admin/social/scrape", response_class=HTMLResponse)
def admin_scrape_form(
    request: Request,
    _: bool = Depends(require_social_admin),
):
    return templates.TemplateResponse(
        "admin_social/scrape.html",
        {"request": request, "key": _admin_key(), "result": None, "error": None, "url": ""},
    )


@router.post("/admin/social/scrape", response_class=HTMLResponse)
async def admin_scrape_run(
    request: Request,
    _: bool = Depends(require_social_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    url = (form.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "URL required")
    result = None
    error = None
    try:
        from api.services import social_scraper
        result = social_scraper.scrape_venue(url)
        sub = UserSubmission(
            submission_type="new_venue",
            payload_json={"scraped": result, "source_url": url},
            submitter_email=None,
            submitter_ip="admin-scrape",
            status="pending",
        )
        db.add(sub)
        db.commit()
    except Exception as e:  # noqa: BLE001 — we want to surface any failure
        log.exception("Scrape failed for %s", url)
        error = str(e)
    return templates.TemplateResponse(
        "admin_social/scrape.html",
        {"request": request, "key": _admin_key(), "url": url, "result": result, "error": error},
    )


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None
