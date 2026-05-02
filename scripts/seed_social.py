"""Seed the /social tables with a starter catalog.

Idempotent — upserts by slug. Re-run safely.

All seeded rows are marked verified=False / source=manual / last_verified_at=NULL
so that the admin "verify before launch" task list in SOCIAL_BUILD_NOTES.md
applies. Nothing here should be considered launch-ready data.

Run:
    python -m scripts.seed_social
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.database import SessionLocal, init_db
from api.models.social import (
    HappyHourSpecial,
    ParkingSpot,
    SocialVenue,
)


# Hours templates ------------------------------------------------------------

HOURS_BAR_LATE = {
    "monday":    {"open": "16:00", "close": "01:00"},
    "tuesday":   {"open": "16:00", "close": "01:00"},
    "wednesday": {"open": "16:00", "close": "01:00"},
    "thursday":  {"open": "16:00", "close": "02:00"},
    "friday":    {"open": "16:00", "close": "03:00"},
    "saturday":  {"open": "12:00", "close": "03:00"},
    "sunday":    {"open": "12:00", "close": "00:00"},
}

HOURS_RESTAURANT = {
    "monday":    {"open": "11:00", "close": "22:00"},
    "tuesday":   {"open": "11:00", "close": "22:00"},
    "wednesday": {"open": "11:00", "close": "22:00"},
    "thursday":  {"open": "11:00", "close": "22:00"},
    "friday":    {"open": "11:00", "close": "23:00"},
    "saturday":  {"open": "10:00", "close": "23:00"},
    "sunday":    {"open": "10:00", "close": "21:00"},
}


# Venue catalog --------------------------------------------------------------
# Format: dict per venue, with `specials` list. Slugs derived from name.

WEEKDAYS = [0, 1, 2, 3, 4]  # Mon–Fri
ALL_DAYS = list(range(7))


def _venue(
    name: str,
    venue_type: str,
    neighborhood: str,
    *,
    address: str | None = None,
    price_tier: int = 2,
    vibe_tags: list[str] | None = None,
    description: str | None = None,
    hours: dict | None = None,
    featured: bool = False,
    specials: list[dict] | None = None,
) -> dict:
    return {
        "name": name,
        "venue_type": venue_type,
        "neighborhood": neighborhood,
        "address": address,
        "price_tier": price_tier,
        "vibe_tags": vibe_tags or [],
        "description": description,
        "hours": hours or HOURS_BAR_LATE,
        "featured": featured,
        "specials": specials or [],
    }


def _hh(
    title: str,
    *,
    days: list[int] = WEEKDAYS,
    start: str = "16:00",
    end: str = "19:00",
    deal_type: str = "drink",
    discount_value: str | None = None,
    description: str | None = None,
) -> dict:
    return {
        "title": title,
        "days_of_week": days,
        "start_time": time.fromisoformat(start),
        "end_time": time.fromisoformat(end),
        "deal_type": deal_type,
        "discount_value": discount_value,
        "description": description,
    }


VENUES: list[dict] = [
    # ----- Broadway (5) -----
    _venue("Tootsie's Orchid Lounge", "music_venue", "Broadway", price_tier=2,
           vibe_tags=["live_music", "tourist_heavy", "dive"], featured=True,
           specials=[
               _hh("$3 Wells Until 6", end="18:00", discount_value="$3 well drinks"),
               _hh("$5 Domestic Pitchers", days=[0, 1, 2], start="14:00", end="17:00",
                   discount_value="$5 domestic pitchers"),
           ]),
    _venue("Robert's Western World", "music_venue", "Broadway", price_tier=2,
           vibe_tags=["live_music", "tourist_heavy", "local_favorite"],
           specials=[
               _hh("Recession Special", days=ALL_DAYS, start="11:00", end="23:00",
                   discount_value="$8 fried bologna + PBR + chips combo",
                   deal_type="both", description="Iconic — runs all day every day."),
               _hh("Sunday Late Show", days=[6], start="22:00", end="01:00",
                   discount_value="$3 PBRs during the late set"),
           ]),
    _venue("Acme Feed & Seed", "restaurant", "Broadway", price_tier=2,
           vibe_tags=["live_music", "patio", "tourist_heavy"],
           hours=HOURS_RESTAURANT,
           specials=[
               _hh("Half-Price Sushi", days=[0, 2], start="15:00", end="18:00",
                   discount_value="50% off rooftop sushi", deal_type="food"),
               _hh("Rooftop Hour", days=WEEKDAYS, start="16:00", end="18:00",
                   discount_value="$5 wells, $6 frozen drinks"),
           ]),
    _venue("The Stage on Broadway", "music_venue", "Broadway", price_tier=2,
           vibe_tags=["live_music", "tourist_heavy"],
           specials=[_hh("$3 Bud Lights", days=WEEKDAYS, start="16:00", end="19:00",
                        discount_value="$3 Bud Lights")]),
    _venue("Whiskey Row", "bar", "Broadway", price_tier=3,
           vibe_tags=["bachelorette_friendly", "tourist_heavy", "rooftop"], featured=True,
           specials=[
               _hh("Industry Tuesday", days=[1], start="22:00", end="02:00",
                   discount_value="50% off for service-industry workers",
                   description="Industry ID required."),
               _hh("Bach Sunday Brunch", days=[6], start="11:00", end="15:00",
                   discount_value="$45 unlimited mimosas + brunch buffet"),
           ]),

    # ----- The Gulch (5) -----
    _venue("L.A. Jackson", "rooftop", "The Gulch", price_tier=4,
           vibe_tags=["rooftop", "date_night", "upscale"], featured=True,
           specials=[
               _hh("Sunset Hour", end="18:30", discount_value="$8 cocktails, $6 wines"),
               _hh("Industry Sunday", days=[6], start="22:00", end="00:00",
                   discount_value="50% off for industry"),
               _hh("Brunch Bubbles", days=[5, 6], start="11:00", end="14:00",
                   discount_value="$25 bottomless mimosas (90 min)",
                   deal_type="drink"),
           ]),
    _venue("Whiskey Kitchen", "restaurant", "The Gulch", price_tier=3,
           vibe_tags=["date_night", "patio", "tourist_heavy"], hours=HOURS_RESTAURANT,
           specials=[
               _hh("Power Hour", end="18:00", deal_type="both",
                   discount_value="$5 wells, $5 select apps"),
               _hh("Late Night Half-Off Pizza", days=[3, 4, 5], start="22:00", end="00:00",
                   discount_value="50% off all pizzas", deal_type="food"),
           ]),
    _venue("Adele's", "restaurant", "The Gulch", price_tier=3,
           vibe_tags=["date_night", "upscale", "patio"], hours=HOURS_RESTAURANT,
           specials=[_hh("Wine-Down Wednesday", days=[2], start="17:00", end="22:00",
                        discount_value="50% off bottles under $100")]),
    _venue("White Limozeen", "rooftop", "The Gulch", price_tier=4,
           vibe_tags=["rooftop", "date_night", "upscale", "bachelorette_friendly"],
           specials=[_hh("Pink Hour", days=[3, 4], start="16:00", end="18:00",
                        discount_value="$10 signature cocktails")]),
    _venue("Sambuca", "music_venue", "The Gulch", price_tier=3,
           vibe_tags=["live_music", "date_night"],
           specials=[_hh("Late Night Bites", days=[3, 4, 5], start="22:00", end="01:00",
                        discount_value="$8 small plates", deal_type="food")]),

    # ----- Germantown (5) -----
    _venue("Henrietta Red", "restaurant", "Germantown", price_tier=4,
           vibe_tags=["date_night", "upscale", "local_favorite"], featured=True,
           hours=HOURS_RESTAURANT,
           specials=[
               _hh("Oyster Hour", days=[1, 2, 3, 4], start="16:30", end="18:00",
                   discount_value="$1.50 oysters + $5 sparkling",
                   deal_type="both", description="Best raw bar deal in the city."),
               _hh("Industry Late Night", days=[6], start="22:00", end="00:00",
                   discount_value="$1 oysters for industry workers",
                   deal_type="food"),
           ]),
    _venue("Rolf and Daughters", "restaurant", "Germantown", price_tier=4,
           vibe_tags=["date_night", "upscale", "local_favorite"], hours=HOURS_RESTAURANT,
           specials=[_hh("Bar Snacks", days=ALL_DAYS, start="17:00", end="18:30",
                        discount_value="$8 bar pasta", deal_type="food")]),
    _venue("Geist Bar & Restaurant", "restaurant", "Germantown", price_tier=3,
           vibe_tags=["patio", "date_night"], hours=HOURS_RESTAURANT,
           specials=[_hh("Patio Hour", days=WEEKDAYS, start="15:00", end="18:00",
                        discount_value="$5 frosé")]),
    _venue("Von Elrod's Beer Hall", "brewery", "Germantown", price_tier=2,
           vibe_tags=["dog_friendly", "patio", "sports", "local_favorite"],
           specials=[
               _hh("Steins Til Six", days=WEEKDAYS, start="14:00", end="18:00",
                   discount_value="$5 large draft pours"),
               _hh("Game Day Pretzels", days=[5, 6], start="12:00", end="18:00",
                   discount_value="$8 giant pretzel + cheese",
                   deal_type="food"),
           ]),
    _venue("Steadfast Coffee", "restaurant", "Germantown", price_tier=2,
           vibe_tags=["dog_friendly", "patio", "local_favorite"],
           hours={**HOURS_RESTAURANT,
                  "monday": {"open": "07:00", "close": "16:00"},
                  "saturday": {"open": "08:00", "close": "16:00"}},
           specials=[_hh("Pastry Power Hour", days=WEEKDAYS, start="14:00", end="16:00",
                        discount_value="Half-priced pastries", deal_type="food")]),

    # ----- East Nashville (5) -----
    _venue("The 5 Spot", "music_venue", "East Nashville", price_tier=2,
           vibe_tags=["live_music", "dive", "local_favorite"], featured=True,
           specials=[
               _hh("Two-Buck Tuesday", days=[1], start="20:00", end="23:00",
                   discount_value="$2 cans + $5 shot+beer combo",
                   description="Hosts the legendary $2 Tuesday Honky-Tonk."),
               _hh("Motown Monday Hour", days=[0], start="20:00", end="22:00",
                   discount_value="$1 off all draft beers"),
               _hh("Sunday Funday", days=[6], start="14:00", end="17:00",
                   discount_value="$3 mimosas + $5 micheladas"),
           ]),
    _venue("Lockeland Table", "restaurant", "East Nashville", price_tier=3,
           vibe_tags=["local_favorite", "date_night"], hours=HOURS_RESTAURANT,
           specials=[_hh("Community Hour", days=WEEKDAYS, start="16:00", end="18:00",
                        discount_value="$6 pizzas, $5 wells",
                        deal_type="both",
                        description="Proceeds support a different East Nash school each month.")]),
    _venue("Pearl Diver", "cocktail_lounge", "East Nashville", price_tier=3,
           vibe_tags=["date_night", "patio", "local_favorite"],
           specials=[
               _hh("Tiki Hour", days=[1, 2, 3, 4], start="17:00", end="19:00",
                   discount_value="$3 off all tiki drinks"),
               _hh("Late Night Mai Tais", days=[5], start="22:00", end="01:00",
                   discount_value="$8 mai tais after 10pm"),
           ]),
    _venue("Dino's", "dive", "East Nashville", price_tier=1,
           vibe_tags=["dive", "local_favorite", "bachelorette_avoid"],
           specials=[_hh("Cheap Beer Hour", days=ALL_DAYS, start="14:00", end="18:00",
                        discount_value="$2 PBR cans, $3 wells")]),
    _venue("Attaboy", "cocktail_lounge", "East Nashville", price_tier=4,
           vibe_tags=["date_night", "upscale", "local_favorite", "bachelorette_avoid"],
           specials=[_hh("Industry Monday", days=[0], start="22:00", end="00:00",
                        discount_value="$2 off classics for industry workers",
                        description="Show service-industry ID at the door.")]),

    # ----- 12 South (5) -----
    _venue("Bastion", "cocktail_lounge", "12 South", price_tier=4,
           vibe_tags=["date_night", "upscale", "local_favorite"], featured=True,
           specials=[
               _hh("Bar Snacks", days=[1, 2, 3, 4], start="17:00", end="18:30",
                   discount_value="$1 nachos with any cocktail purchase",
                   deal_type="food", description="The cult $1 nacho is the anchor."),
               _hh("Late Night Tasting", days=[3, 4], start="22:00", end="00:00",
                   discount_value="$15 tasting flight"),
           ]),
    _venue("Burger Up", "restaurant", "12 South", price_tier=2,
           vibe_tags=["patio", "dog_friendly", "local_favorite"], hours=HOURS_RESTAURANT,
           specials=[_hh("Hooch Hour", days=WEEKDAYS, start="16:00", end="18:00",
                        discount_value="$5 select cocktails + $4 well",
                        deal_type="drink")]),
    _venue("Edley's Bar-B-Que", "restaurant", "12 South", price_tier=2,
           vibe_tags=["patio", "dog_friendly", "local_favorite", "sports"],
           hours=HOURS_RESTAURANT,
           specials=[
               _hh("Tipsy Tuesday", days=[1], start="11:00", end="22:00",
                   discount_value="$5 frozen Tipsy Pig"),
               _hh("Wing Wednesday", days=[2], start="16:00", end="20:00",
                   discount_value="50¢ wings, $4 select drafts",
                   deal_type="both"),
           ]),
    _venue("Mafiaoza's", "restaurant", "12 South", price_tier=2,
           vibe_tags=["patio", "local_favorite"], hours=HOURS_RESTAURANT,
           specials=[
               _hh("Slice + Pint", days=WEEKDAYS, start="15:00", end="18:00",
                   discount_value="$8 slice + draft", deal_type="both"),
               _hh("Late Night Half-Off Bottles", days=[4, 5], start="22:00", end="00:00",
                   discount_value="50% off bottles of wine"),
           ]),
    _venue("Frothy Monkey", "restaurant", "12 South", price_tier=2,
           vibe_tags=["dog_friendly", "patio", "local_favorite"],
           hours={**HOURS_RESTAURANT,
                  "monday": {"open": "07:00", "close": "21:00"}},
           specials=[_hh("Wine + Cheese Hour", days=[2, 3, 4], start="16:00", end="18:00",
                        discount_value="$5 wine pours, $3 off cheese boards",
                        deal_type="both")]),

    # ----- Midtown (5) -----
    _venue("Patterson House", "cocktail_lounge", "Midtown", price_tier=4,
           vibe_tags=["date_night", "upscale", "local_favorite", "bachelorette_avoid"],
           featured=True,
           specials=[_hh("Bartender's Choice", days=[1], start="17:00", end="19:00",
                        discount_value="$10 off-menu cocktail of the day",
                        description="Tuesdays only. Cash bar; no parties >4.")]),
    _venue("Tin Roof Demonbreun", "bar", "Midtown", price_tier=2,
           vibe_tags=["live_music", "sports", "bachelorette_friendly", "tourist_heavy"],
           specials=[
               _hh("Industry Hour", days=[0], start="22:00", end="01:00",
                   discount_value="$3 wells, $4 calls — service ID"),
               _hh("Bach Saturday", days=[5], start="14:00", end="17:00",
                   discount_value="$30 bottomless mimosas for parties of 4+",
                   description="Bachelorette parties only — call ahead."),
           ]),
    _venue("Loser's", "bar", "Midtown", price_tier=2,
           vibe_tags=["live_music", "sports", "local_favorite", "dive"],
           specials=[
               _hh("Power Hour", days=WEEKDAYS, start="16:00", end="19:00",
                   discount_value="$3 domestic, $4 imports, $5 wells"),
               _hh("Karaoke Sunday", days=[6], start="21:00", end="00:00",
                   discount_value="$3 wells while you sing"),
           ]),
    _venue("Kayne Prime", "restaurant", "Midtown", price_tier=4,
           vibe_tags=["upscale", "date_night"], hours=HOURS_RESTAURANT,
           specials=[_hh("Bar-Side Steakhouse Snacks", days=ALL_DAYS, start="16:30", end="18:00",
                        discount_value="$8 wagyu sliders, $9 espresso martini",
                        deal_type="both")]),
    _venue("Hopdoddy Burger Bar", "restaurant", "Midtown", price_tier=2,
           vibe_tags=["patio", "dog_friendly"], hours=HOURS_RESTAURANT,
           specials=[
               _hh("Happy Hour", days=WEEKDAYS, start="15:00", end="18:00",
                   discount_value="$2 off draft, $5 truffle fries",
                   deal_type="both"),
               _hh("Burger of the Month", days=ALL_DAYS, start="11:00", end="22:00",
                   discount_value="$3 off rotating burger of the month",
                   deal_type="food"),
           ]),

    # ----- Wedgewood-Houston (5) -----
    _venue("Bastion (WeHo)", "cocktail_lounge", "Wedgewood-Houston", price_tier=4,
           vibe_tags=["upscale", "local_favorite"],
           specials=[_hh("Bar-Side Snacks", days=[2, 3, 4], start="17:00", end="18:30",
                        discount_value="$1 nachos with cocktail purchase",
                        deal_type="food")]),
    _venue("Diskin Cider", "brewery", "Wedgewood-Houston", price_tier=2,
           vibe_tags=["dog_friendly", "patio", "local_favorite"],
           specials=[_hh("Cider Down", days=[2, 3, 4], start="16:00", end="18:00",
                        discount_value="$2 off pints")]),
    _venue("Jackalope Brewing - The Ranch", "brewery", "Wedgewood-Houston",
           price_tier=2, vibe_tags=["dog_friendly", "patio", "local_favorite"],
           specials=[_hh("Pint Night", days=[2], start="17:00", end="20:00",
                        discount_value="$5 pints + free pint glass for first 50")]),
    _venue("Falcon Coffee Bar", "restaurant", "Wedgewood-Houston", price_tier=2,
           vibe_tags=["dog_friendly", "patio", "local_favorite"],
           hours={"monday": {"open": "07:00", "close": "15:00"},
                  "tuesday": {"open": "07:00", "close": "15:00"},
                  "wednesday": {"open": "07:00", "close": "15:00"},
                  "thursday": {"open": "07:00", "close": "15:00"},
                  "friday": {"open": "07:00", "close": "15:00"},
                  "saturday": {"open": "08:00", "close": "15:00"},
                  "sunday": {"open": "08:00", "close": "15:00"}},
           specials=[_hh("Espresso Hour", days=WEEKDAYS, start="07:00", end="09:00",
                        discount_value="$1 off espresso drinks",
                        deal_type="drink")]),
    _venue("Trax Coffee + Cocktails", "cocktail_lounge", "Wedgewood-Houston",
           price_tier=2, vibe_tags=["patio", "dog_friendly", "local_favorite"],
           specials=[_hh("Espresso Martini Hour", days=[3, 4], start="16:00", end="19:00",
                        discount_value="$8 espresso martinis")]),

    # ----- Donelson + Sylvan Park (5 to bring total ≥40) -----
    _venue("Park Cafe", "restaurant", "Sylvan Park", price_tier=3,
           vibe_tags=["date_night", "local_favorite"], hours=HOURS_RESTAURANT,
           specials=[_hh("Neighborhood Hour", days=WEEKDAYS, start="17:00", end="19:00",
                        discount_value="$5 wines + half-priced burger",
                        deal_type="both")]),
    _venue("McCabe Pub", "bar", "Sylvan Park", price_tier=2,
           vibe_tags=["sports", "local_favorite", "dive"],
           specials=[
               _hh("Pub Hour", days=ALL_DAYS, start="15:00", end="18:00",
                   discount_value="$3 domestics, $1 off everything"),
               _hh("Trivia Tuesday Pints", days=[1], start="19:00", end="22:00",
                   discount_value="$4 draft pints during trivia"),
           ]),
    _venue("The Sutler Saloon", "music_venue", "Sylvan Park", price_tier=3,
           vibe_tags=["live_music", "local_favorite"],
           specials=[
               _hh("Sutler Hour", days=[1, 2, 3], start="17:00", end="19:00",
                   discount_value="$4 wells, $5 select cocktails"),
               _hh("Songwriter Sunday", days=[6], start="18:00", end="21:00",
                   discount_value="$1 off all draft beers during the round"),
           ]),
    _venue("Two Bits", "bar", "Donelson", price_tier=2,
           vibe_tags=["dive", "sports", "local_favorite"],
           specials=[_hh("All Day Cheap", days=ALL_DAYS, start="11:00", end="20:00",
                        discount_value="$3 domestic cans, $4 wells")]),
    _venue("Center Point Bar-B-Que", "restaurant", "Donelson", price_tier=2,
           vibe_tags=["local_favorite"], hours=HOURS_RESTAURANT,
           specials=[_hh("Lunch Combo Deal", days=WEEKDAYS, start="11:00", end="14:00",
                        discount_value="$10 sandwich + side + drink combo",
                        deal_type="both")]),
]


PARKING: list[dict] = [
    {"name": "Premier Parking — 5th & Demonbreun", "near_neighborhood": "Broadway",
     "parking_type": "garage", "nightly_rate": "$25", "event_rate": "$40",
     "address": "150 5th Ave S, Nashville, TN 37203",
     "notes": "Closest covered garage to Broadway honky-tonks. Cash + card."},
    {"name": "SP+ — 11th & McGavock", "near_neighborhood": "The Gulch",
     "parking_type": "lot", "nightly_rate": "$15", "event_rate": "$25",
     "notes": "Best Gulch deal after 6pm — pay-by-app."},
    {"name": "5th & Madison surface lot", "near_neighborhood": "Germantown",
     "parking_type": "lot", "nightly_rate": "$10",
     "notes": "Plenty of street parking nearby on weeknights."},
    {"name": "East Nashville street parking", "near_neighborhood": "East Nashville",
     "parking_type": "street", "nightly_rate": "Free",
     "notes": "Free side-street parking off 11th, 14th, Riverside. Don't block driveways."},
    {"name": "12 South side-street parking", "near_neighborhood": "12 South",
     "parking_type": "street", "nightly_rate": "Free",
     "notes": "Use the residential streets east of 12th — pay attention to 'no parking' Sat/Sun for tour buses."},
    {"name": "Midtown — Premier 21st & Broadway", "near_neighborhood": "Midtown",
     "parking_type": "garage", "nightly_rate": "$18", "event_rate": "$30"},
    {"name": "WeHo — Houston Station Lot", "near_neighborhood": "Wedgewood-Houston",
     "parking_type": "lot", "nightly_rate": "Free with patronage",
     "notes": "Free if you patronize the businesses — strictly enforced after 9pm."},
]


def _slugify(text: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def upsert():
    init_db()
    db = SessionLocal()
    venue_added = venue_updated = special_added = 0
    parking_added = 0
    try:
        for v in VENUES:
            slug = _slugify(v["name"])
            row = db.query(SocialVenue).filter(SocialVenue.slug == slug).first()
            if row is None:
                row = SocialVenue(
                    slug=slug,
                    name=v["name"],
                    venue_type=v["venue_type"],
                    neighborhood=v["neighborhood"],
                    address=v["address"],
                    price_tier=v["price_tier"],
                    vibe_tags=v["vibe_tags"],
                    description=v["description"],
                    hours_json=v["hours"],
                    featured=v["featured"],
                    verified=False,
                    last_verified_at=None,
                )
                db.add(row)
                db.flush()
                venue_added += 1
            else:
                row.name = v["name"]
                row.venue_type = v["venue_type"]
                row.neighborhood = v["neighborhood"]
                row.address = v["address"]
                row.price_tier = v["price_tier"]
                row.vibe_tags = v["vibe_tags"]
                row.description = v["description"]
                row.hours_json = v["hours"]
                row.featured = v["featured"]
                venue_updated += 1

            existing_titles = {s.title for s in row.specials}
            for s in v["specials"]:
                if s["title"] in existing_titles:
                    continue
                db.add(HappyHourSpecial(
                    venue_id=row.id,
                    title=s["title"],
                    description=s.get("description"),
                    days_of_week=s["days_of_week"],
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    deal_type=s["deal_type"],
                    discount_value=s.get("discount_value"),
                    source="manual",
                    active=True,
                ))
                special_added += 1

        for p in PARKING:
            existing = db.query(ParkingSpot).filter(ParkingSpot.name == p["name"]).first()
            if existing:
                continue
            db.add(ParkingSpot(
                name=p["name"],
                address=p.get("address"),
                parking_type=p.get("parking_type", "lot"),
                nightly_rate=p.get("nightly_rate"),
                event_rate=p.get("event_rate"),
                notes=p.get("notes"),
                near_neighborhood=p.get("near_neighborhood"),
                active=True,
            ))
            parking_added += 1

        db.commit()
    finally:
        db.close()
    print(f"Seeded venues: +{venue_added} new, {venue_updated} updated")
    print(f"Seeded specials: +{special_added}")
    print(f"Seeded parking: +{parking_added}")
    print(f"Total venues in catalog: {len(VENUES)}")
    print(f"Total specials in catalog: {sum(len(v['specials']) for v in VENUES)}")


if __name__ == "__main__":
    upsert()
