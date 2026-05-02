# NashGuide AI

Automated Nashville trip planner. Agent swarm that handles intake → payment → itinerary generation → PDF delivery → marketing → venue freshness.

## Quick start

```bash
cp .env.example .env
# fill in PAYPAL_*, ANTHROPIC_API_KEY, RESEND_API_KEY, ADMIN_KEY, SECRET_KEY
docker compose up -d --build
curl -X POST "http://localhost:8080/admin/venues/seed?key=$ADMIN_KEY"
```

API: http://localhost:8080
Admin: http://localhost:8080/admin/dashboard?key=YOUR_ADMIN_KEY

## Services (docker-compose)
- `nashguide-api` — FastAPI on :8080
- `nashguide-workers` — Planner + Delivery + Marketing + Updater agents
- `nashguide-postgres` — Postgres 16
- `nashguide-redis` — Redis 7

## Product tiers
| Tier | Price | Includes |
|---|---|---|
| Classic | $9.99 | Personalized itinerary (PDF + web link) |
| VIP | $29.99 | Classic + reservation links + hidden gems + packing list + Spotify |
| Bachelorette | $19.99 | Specialized bachelorette itinerary + bar crawl + photo spots |

## Architecture
See `agents/souls/*.md` for the personality + responsibilities of each agent.

Flow:
1. **Intake** — `/api/quiz/start` → `/api/quiz/submit` → `/api/payment/create` → PayPal → `/api/payment/capture`
2. Payment capture enqueues `nashguide:jobs:itinerary` in Redis.
3. **Planner** blocks on that queue, pulls matching venues, calls Claude, saves itinerary, enqueues `nashguide:jobs:delivery`.
4. **Delivery** renders PDF (WeasyPrint) + web page, sends Resend email with PDF attachment, schedules reminder.
5. **Marketing** runs on cron (APScheduler): tweets daily 9am, blog Mondays 10am.
6. **Updater** sweeps venues Sundays 4am.

## `/social` — Nashville Happy Hours & Specials

A separate vertical living on the same host: the live source of truth for
Nashville happy hours, drink/food specials, and venue specials. Mobile-first.

- Public landing: `/social` — sticky "Happy Now" pill on every page.
- Live JSON: `/social/now` (active specials, America/Chicago).
- Master schedule: `/social/happy-hours`.
- Submissions: `/social/submit` (rate-limited, honeypot-protected).
- Advertising: `/social/advertise` (three packages, lead form).
- Admin: `/admin/social?key=$NASHGUIDE_ADMIN_KEY` — moderation queue, venue
  CRUD, ad placements, AI scrape stub.

Set up:

```bash
echo 'NASHGUIDE_ADMIN_KEY=<random>' >> .env
docker compose exec api alembic upgrade head    # create the 5 social tables
docker compose exec api python -m scripts.seed_social  # 40 venues, 60 specials, 7 parking
```

Full deploy notes & pre-launch verification checklist: see `SOCIAL_BUILD_NOTES.md`.

## Deployment (Hetzner 87.99.137.43 alongside NASHTY)

Runs on port 8080 — NASHTY stays on 80. If you want to share the existing NASHTY postgres/redis instead of spinning up new ones, edit `docker-compose.yml` to remove `nashguide-postgres` / `nashguide-redis` services and point `DATABASE_URL` / `REDIS_URL` at the NASHTY containers by their network alias.

```bash
ssh root@87.99.137.43
cd /opt/nashguide
git pull
docker compose up -d --build
```
