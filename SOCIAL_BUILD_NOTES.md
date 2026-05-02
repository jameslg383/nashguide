# NashGuide `/social` — build notes

A new vertical that turns NashGuide into the live source of truth for Nashville
happy hours, drink/food specials, and venue specials. This document covers
what was built, deferred, the deploy steps for the Hetzner box, and the
pre-launch verification checklist.

## What was built

### Backend
- `api/models/social.py` — five SQLAlchemy models: `SocialVenue`,
  `HappyHourSpecial`, `ParkingSpot`, `UserSubmission`, `AdPlacement`. Uses
  generic JSON columns for arrays so `init_db()` works against SQLite (tests)
  and Postgres (prod).
- `api/routes/social.py` — single router exposing every public + admin route.
- `api/services/social_scraper.py` — LLM-driven extraction stub. Reuses the
  existing Anthropic client. Always routes results through
  `user_submissions` for human approval.
- `alembic/env.py` + `alembic/versions/20260502_01_add_social_tables.py` —
  bootstraps Alembic for the project (was configured but unused) and adds
  the social tables with proper Postgres `ARRAY` columns + GIN indexes.

### Public routes (anonymous)
| Route | Purpose |
|---|---|
| `GET /social` | Landing — "What's happy now?" hero, featured venues, neighborhood grid, vibe chips. |
| `GET /social/now` | JSON of every special active this exact minute (America/Chicago). Powers the sticky drawer. |
| `GET /social/venues` | Filtered/paginated venue list. Filters: neighborhood, vibe, type, has_happy_hour, open_now, q. |
| `GET /social/venues/{slug}` | Venue detail: today's specials box, full week table, hours, JSON-LD `LocalBusiness`/`FoodEstablishment`. |
| `GET /social/neighborhoods/{slug}` | Neighborhood roll-up sorted by "happiest right now". |
| `GET /social/happy-hours` | Master schedule, day tabs, time-slot accordions, neighborhood filter. |
| `GET /social/parking` | Parking spots, optional `?near=` filter. |
| `GET /social/submit` | Three-flow submission form (new venue / new special / correction / closed). |
| `POST /social/submit` | Honeypot + min-time + per-IP rate-limit (5/hr). Drops to `user_submissions` pending. |
| `GET /social/advertise` | Three packages, lead form. |
| `POST /social/advertise` | Drops `ad_inquiry` row into submissions queue. |
| `GET /social/ad/{id}/click` | Counts and 302-redirects. |
| `GET /social/sitemap.xml` | Crawlable sitemap of every venue + neighborhood. |

### Admin (gated by `?key=NASHGUIDE_ADMIN_KEY`)
| Route | Purpose |
|---|---|
| `GET /admin/social` | Counts dashboard. |
| `GET /admin/social/submissions` | Moderation queue. Approve upserts to live tables; reject saves notes. |
| `GET /admin/social/venues` | Venue list with verify + show/hide buttons. |
| `GET /admin/social/specials` | Special list with bulk-deactivate-stale (>90d). |
| `GET /admin/social/ads` | Create/list/pause ads. |
| `GET /admin/social/ads/export` | CSV export of impressions/clicks/CTR. |
| `GET /admin/social/scrape` | Form. Posts a URL → LLM extraction → submission queue. |

### Templates
- `api/templates/social/_base.html` — shared dark/amber layout matching the
  existing itinerary aesthetic. Includes the **sticky "Happy Now" pill +
  bottom drawer** that fetches `/social/now`.
- Per-page templates: `landing`, `venues_list`, `venue_detail`,
  `neighborhood`, `happy_hours`, `parking`, `submit`, `submit_thanks`,
  `advertise`.
- `api/templates/admin_social/*` — admin pages (submissions, venues,
  specials, ads, scrape).

### Seed data
- `scripts/seed_social.py` — 40 venues across 9 neighborhoods (Broadway, The
  Gulch, Germantown, East Nashville, 12 South, Midtown, Wedgewood-Houston,
  Sylvan Park, Donelson) with **60 specials total**, plus 7 parking spots.
- All seeded rows are flagged `verified=False` and `last_verified_at=NULL`
  — they're scaffolding, not launch data.
- Idempotent — upserts by `slug`, never duplicates specials.

### Tests (`tests/social/`)
- `test_migration.py` — migration module imports cleanly; metadata create/drop round-trips.
- `test_happy_now.py` — `/social/now` returns Tue-only special at frozen `Tue 5pm`, returns nothing at `Tue 11am`, never returns inactive rows.
- `test_submissions.py` — successful submission persists; honeypot silently swallows; 6th request from same IP within an hour gets 429.
- `test_admin_and_ads.py` — every admin path 401s without/with-wrong key, 200s with correct key; ad click increments counter and 302-redirects; missing ad 404s.
- 12 new tests, all green. Existing smoke tests still pass.

## Web scraping (Firecrawl)

A scheduled scraper agent + admin tooling now drives ingestion. **Output
always lands in the moderation queue — never live tables.**

- **`api/services/firecrawl_client.py`** — thin wrapper over the Firecrawl
  SDK. Disconnected unless `FIRECRAWL_API_KEY` is set; falls back to plain
  httpx in that case.
- **`api/services/social_scraper.py`** — pipeline split into `fetch_page`
  (Firecrawl-or-httpx) and `extract_from_text` (Anthropic). `scrape_venue`
  composes them.
- **`agents/social_scraper_agent.py`** — runs as a thread inside
  `agents/run_all.py`. APScheduler drives:
  - daily-frequency sources at 03:30 CT every day,
  - weekly-frequency sources at 04:30 CT on Sundays,
  - manual-frequency sources only on admin-triggered run-now.
  Per-source 4-second delay, 50-source-per-run cap, fault-tolerant
  (one failure won't stop the loop; it's logged on the source row).
- **New table `scrape_sources`** — URLs to monitor, with `source_type`
  (`venue_page` for 1:1 pages, `listing_page` for roundup articles), label,
  frequency, last_scraped_at, last_status, last_error, last_specials_found.
  Migration `20260502_02_add_scrape_sources`.
- **Admin UI at `/admin/social/scrape`** — list/add/run-now/pause/delete
  sources, Firecrawl-powered web search to discover candidate URLs (one
  click "+ Track" to schedule them), one-off scrape input for testing.

The scrape agent and Firecrawl integration honor existing kill switches:
- `SOCIAL_SCRAPER_ENABLED=false` → agent skips its sweeps.
- `FIRECRAWL_API_KEY` empty → all fetches fall back to httpx; nothing breaks.

## What was deferred

- **Auto-merging scraped specials.** Findings always require a human click
  in the moderation queue. Could be lifted with a confidence-score field
  later, but the right MVP is human-in-the-loop.
- **Firecrawl crawl mode** (recursively expand a venue's site to find a
  hidden /happy-hour page). Single-page `/scrape` is enough for v1.
- **Photo uploads.** Venue detail templates have a placeholder where photos
  would slot. We didn't build the upload pipeline — venues currently use
  text + map link only.
- **Map view.** Detail page has a "Open in Google Maps" link rather than an
  embedded Maps iframe, to avoid a Maps API key dependency. The data is
  there (`lat`/`lng`); just slot a `<iframe>` if/when desired.
- **Sub-domain.** Stays on `nashguide.online/social` per the spec.
- **PayPal-backed advertiser self-service.** Inquiries go to the moderation
  queue; admin manually creates the ad placement row after talking to the
  advertiser.
- **Discount codes for specials** (e.g. show-this-page-for-deal). Out of
  scope; can add a `coupon_code` text field to `happy_hour_specials` later.
- **Replacing the in-memory rate limiter with Redis.** Fine for current
  traffic; the existing `_redis` client is available if it ever matters.

## Decisions made

- **Router lives at `api/routes/social.py`** (not `app/routers/`) because
  the rest of the project uses `api/routes/`. Same convention as `quiz`,
  `payment`, `promo`, etc.
- **Admin auth uses `?key=` pattern** matching `api/routes/admin.py`. The
  alternate session-based admin (`admin_console.py`) was *not* extended
  because: (a) the spec explicitly called for `?key=`, (b) the social-admin
  surface is small enough that bookmarking a key URL is fine.
- **Admin key resolution is env-first**, settings-fallback. This makes
  test monkeypatching work without rebuilding the Pydantic Settings
  singleton, and is robust against env changes between deploys.
- **Array columns are JSON in models, ARRAY+GIN in the migration.** That
  way `init_db()` (which does `metadata.create_all`) keeps working on
  SQLite for tests, while prod gets the right Postgres types via Alembic.
  *Trade-off:* if you only run `init_db()` in prod (skipping Alembic), you
  lose the GIN index on `vibe_tags`. Run the migration.
- **Happy-now math is server-side**, not JS-clock. The browser's clock is
  unreliable; CT is what matters. We compute in `America/Chicago`.
- **Honeypot + min-time-on-page**, not captcha. CAPTCHA hurts the form;
  these two checks kill 95%+ of bot traffic without UX cost.
- **The "Happy Now" sticky pill is the killer feature.** It's the
  default-visible affordance on every page; opens a drawer that calls
  `/social/now` once and renders the cards.

## Pre-launch venue verification checklist (admin task)

The seeded venues are real Nashville names but nothing was independently
verified. Before public launch, an admin should walk this list, confirm
addresses/hours/specials with the venue website or a phone call, and click
**Verify** in `/admin/social/venues`.

Suggested order (highest-traffic first):
1. **Broadway** — Tootsie's, Robert's, Acme, The Stage, Whiskey Row.
2. **The Gulch** — L.A. Jackson, Whiskey Kitchen, Adele's, White Limozeen, Sambuca.
3. **Germantown** — Henrietta Red, Rolf and Daughters, Geist, Von Elrod's, Steadfast.
4. **East Nashville** — The 5 Spot, Lockeland Table, Pearl Diver, Dino's, Attaboy.
5. **12 South** — Bastion, Burger Up, Edley's, Mafiaoza's, Frothy Monkey.
6. **Midtown** — Patterson House, Tin Roof, Loser's, Kayne Prime, Hopdoddy.
7. **Wedgewood-Houston** — Bastion (WeHo), Diskin Cider, Jackalope, Falcon, Trax.
8. **Sylvan Park** — Park Cafe, McCabe Pub, The Sutler Saloon.
9. **Donelson** — Two Bits, Center Point Bar-B-Que.

Things to specifically confirm:
- The address (we left them mostly blank) → fill in via the admin venue edit screen.
- That the venue still exists (Nashville turns over fast).
- The exact start/end times of advertised specials.
- "Industry only" / "Service ID required" — easy to mis-cite.

## Deployment to Hetzner

The prod box is `37.27.213.238` running the `nashguide.online` Caddy +
Docker setup.

```bash
ssh root@37.27.213.238
cd /opt/nashguide   # adjust to actual deploy root

git pull origin claude/nashguide-social-build-f3YLU   # or main, after merge

# 1. Add the env vars (once)
echo 'NASHGUIDE_ADMIN_KEY=<pick-a-strong-random-string>' >> .env
echo 'FIRECRAWL_API_KEY=<your-firecrawl-key-or-leave-blank>' >> .env
echo 'SOCIAL_SCRAPER_ENABLED=true' >> .env

# 2. Rebuild + restart so the new code + env are picked up
docker compose build api
docker compose up -d api

# 3. Apply the migration. Two options:
#    A) Alembic (preferred, gets the Postgres ARRAY/GIN indexes):
docker compose exec api alembic upgrade head

#    B) Or just let the FastAPI startup hook auto-create via init_db()
#       (Falls back to JSON columns; loses the GIN index on vibe_tags.)
docker compose restart api

# 4. Seed the catalog (idempotent — safe to re-run)
docker compose exec api python -m scripts.seed_social

# 5. Smoke-check
curl -s https://nashguide.online/social/now | head -c 200
curl -s -o /dev/null -w '%{http_code}\n' https://nashguide.online/social

# 6. Open the admin and start verifying venues
open "https://nashguide.online/admin/social?key=<NASHGUIDE_ADMIN_KEY>"
```

DNS / Caddy: no changes needed. Routes live under `/social` on the existing
`nashguide.online` host.

### Rollback

```bash
docker compose exec api alembic downgrade -1   # drops the 5 social tables
git checkout main && docker compose build api && docker compose up -d api
```

The migration only adds tables — there are no destructive changes to
existing data.

## Files added / changed

```
alembic/env.py                                                  (new)
alembic/script.py.mako                                          (new)
alembic/versions/20260502_01_add_social_tables.py               (new)
alembic/versions/20260502_02_add_scrape_sources.py              (new)
api/models/social.py                                            (new — 6 models)
api/services/social_scraper.py                                  (new)
api/services/firecrawl_client.py                                (new)
api/routes/social.py                                            (new)
api/templates/social/*.html                                     (new — 9 files)
api/templates/admin_social/*.html                               (new — 6 files)
agents/social_scraper_agent.py                                  (new — APScheduler-based)
scripts/seed_social.py                                          (new)
tests/social/*.py                                               (new — 7 files inc. conftest)
SOCIAL_BUILD_NOTES.md                                           (new — this file)

agents/run_all.py                                               (added social_scraper thread)
api/main.py                                                     (added social router)
api/models/database.py                                          (added social to init_db imports)
api/config.py                                                   (NASHGUIDE_ADMIN_KEY, FIRECRAWL_API_KEY, SOCIAL_SCRAPER_ENABLED, social_default_tz)
.env.example                                                    (new env vars)
requirements.txt                                                (firecrawl-py)
README.md                                                       (/social section)
```
