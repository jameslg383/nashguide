"""Unified admin console — session-auth'd dashboard with orders, IPs, analytics, funnel, events.

Login is at /admin/login. Sessions live in an HMAC-signed cookie (30 days).
All /admin/console and /api/admin/* routes require a valid session.
"""
import hmac
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import settings
from api.models.database import get_db

log = logging.getLogger("admin_console")
router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


# -- Auth --------------------------------------------------------------------


def require_admin(request: Request):
    """Dependency — redirects to /admin/login if session is missing."""
    user = request.session.get("admin_user")
    if not user:
        # For HTML routes we want a redirect; for API routes 401 is cleaner.
        # We encode the path here and let the caller decide via the Location header.
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Session", "X-Redirect-To": "/admin/login"},
        )
    return user


def require_admin_or_redirect(request: Request):
    """HTML variant — raises a 303 redirect to /admin/login instead of 401."""
    user = request.session.get("admin_user")
    if not user:
        raise HTTPException(
            status_code=303,
            detail="Not authenticated",
            headers={"Location": "/admin/login"},
        )
    return user


# -- Login / logout ---------------------------------------------------------


LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NashGuide Admin · Sign in</title>
<style>
  :root { --red:#c8102e; --amber:#f59e0b; --bg:#0a0a0f; --card:#1a1a1c; --ink:#f4f4f4; --muted:#9ca3af; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--ink); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .card { background: var(--card); border: 1px solid #2a2a30; border-radius: 14px; padding: 36px; width: 100%; max-width: 400px; box-shadow: 0 20px 60px rgba(0,0,0,.5); }
  .brand { color: var(--amber); letter-spacing: 2px; text-transform: uppercase; font-size: 12px; font-weight: 700; }
  h1 { font-size: 24px; margin: 6px 0 4px; }
  .sub { color: var(--muted); font-size: 14px; margin-bottom: 24px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
  input { width: 100%; padding: 12px 14px; background: #0f0f13; border: 1px solid #2a2a30; border-radius: 8px; color: var(--ink); font-size: 15px; outline: none; margin-bottom: 16px; font-family: inherit; }
  input:focus { border-color: var(--amber); }
  button { width: 100%; padding: 13px; background: linear-gradient(to right, var(--amber), #f97316); color: #000; font-weight: 700; font-size: 15px; border: none; border-radius: 8px; cursor: pointer; font-family: inherit; }
  button:hover { transform: translateY(-1px); }
  .err { background: rgba(200,16,46,.1); border: 1px solid rgba(200,16,46,.3); color: #ff9aa5; padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
</style>
</head>
<body>
<form class="card" method="post" action="/admin/login">
  <div class="brand">NashGuide Admin</div>
  <h1>Sign in</h1>
  <p class="sub">Only authorized operators.</p>
  __ERROR__
  <label>Username</label>
  <input name="username" autocomplete="username" autofocus required>
  <label>Password</label>
  <input name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Sign in</button>
</form>
</body>
</html>"""


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, error: str = ""):
    # If already logged in, go straight to console
    if request.session.get("admin_user"):
        return RedirectResponse(url="/admin/console", status_code=303)
    err_html = f'<div class="err">{error}</div>' if error else ""
    return HTMLResponse(LOGIN_PAGE.replace("__ERROR__", err_html))


@router.post("/admin/login", include_in_schema=False)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # Constant-time compare to avoid timing leaks
    user_ok = hmac.compare_digest(username, settings.admin_user)
    pass_ok = hmac.compare_digest(password, settings.admin_pass)
    if not (user_ok and pass_ok):
        log.warning("Failed admin login attempt (user=%r from ip=%s)", username, request.client.host if request.client else "?")
        return RedirectResponse(
            url="/admin/login?error=" + "Invalid+credentials",
            status_code=303,
        )
    request.session["admin_user"] = settings.admin_user
    request.session["login_at"] = datetime.utcnow().isoformat()
    log.info("Admin login success (user=%s ip=%s)", settings.admin_user, request.client.host if request.client else "?")
    return RedirectResponse(url="/admin/console", status_code=303)


@router.get("/admin/logout", include_in_schema=False)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


# -- Dashboard ---------------------------------------------------------------


@router.get("/admin/console", response_class=HTMLResponse, include_in_schema=False)
async def admin_console(_: str = Depends(require_admin_or_redirect)):
    p = STATIC_DIR / "admin.html"
    if p.exists():
        return FileResponse(str(p))
    raise HTTPException(status_code=404, detail="admin.html not found in /static/")


# -- Unified data API --------------------------------------------------------


@router.get("/api/admin/whoami")
async def whoami(user: str = Depends(require_admin)):
    return {"user": user}


def _ensure_analytics_table(db: Session):
    """Safety net — matches the one in analytics.py."""
    try:
        db.execute(text("SELECT 1 FROM analytics_events LIMIT 1"))
    except Exception:
        db.rollback()


@router.get("/api/admin/data")
async def admin_data(
    period: str = "30d",
    user: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Single consolidated dashboard payload. Pulls from every data source in one call."""
    days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}
    days = days_map.get(period, 30)
    since = datetime.utcnow() - timedelta(days=days)

    _ensure_analytics_table(db)

    def q(sql, params=None):
        p = dict(params or {})
        p.setdefault("since", since)
        return db.execute(text(sql), p).fetchall()

    def q1(sql, params=None):
        p = dict(params or {})
        p.setdefault("since", since)
        return db.execute(text(sql), p).fetchone()

    try:
        # -- Analytics overview (bots filtered out for "real" numbers) --
        overview = q1("""
            SELECT COUNT(*), COUNT(DISTINCT visitor_id), COUNT(DISTINCT session_id), COUNT(DISTINCT ip)
            FROM analytics_events
            WHERE created_at >= :since AND (is_bot = false OR is_bot IS NULL)
        """)
        bots = q1("""
            SELECT COUNT(*), COUNT(DISTINCT ip)
            FROM analytics_events
            WHERE created_at >= :since AND is_bot = true
        """)

        # -- Revenue --
        rev = q1("""
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('paid','delivered') THEN amount ELSE 0 END), 0),
                COUNT(CASE WHEN status IN ('paid','delivered') THEN 1 END),
                COUNT(CASE WHEN status = 'pending' THEN 1 END),
                COUNT(CASE WHEN status = 'failed' THEN 1 END),
                COUNT(*)
            FROM orders
            WHERE created_at >= :since
        """)
        paid_rev, paid_orders, pending_orders, failed_orders, total_orders_period = rev
        arpu = (float(paid_rev) / paid_orders) if paid_orders else 0

        # All-time revenue
        all_rev = q1("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM orders WHERE status IN ('paid','delivered')", {})

        # -- Funnel --
        funnel_steps = ['page_view', 'quiz_start', 'quiz_step', 'quiz_complete',
                        'tier_view', 'tier_select', 'checkout_start', 'payment_start']
        steps_sql = "(" + ",".join(f"'{s}'" for s in funnel_steps) + ")"
        frows = q(f"""
            SELECT event_type, COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type IN {steps_sql} AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY event_type
        """)
        fcounts = {r[0]: r[1] for r in frows}
        funnel = [{"step": s, "visitors": fcounts.get(s, 0)} for s in funnel_steps]
        funnel.append({"step": "payment_success", "visitors": paid_orders})

        # -- Time series: events/day and revenue/day (last 30 days) --
        events_series = q("""
            SELECT date_trunc('day', created_at) AS d,
                   COUNT(*) AS events,
                   COUNT(DISTINCT visitor_id) AS visitors
            FROM analytics_events
            WHERE created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY d ORDER BY d
        """)
        rev_series = q("""
            SELECT date_trunc('day', created_at) AS d,
                   COUNT(*) AS orders,
                   COALESCE(SUM(amount), 0) AS revenue
            FROM orders
            WHERE created_at >= :since AND status IN ('paid','delivered')
            GROUP BY d ORDER BY d
        """)

        # -- Orders (recent 200) --
        orders = q("""
            SELECT o.id, o.product_type, o.amount, o.status, o.paypal_order_id, o.created_at,
                   c.email, c.name, c.id AS cid
            FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
            WHERE o.created_at >= :since
            ORDER BY o.created_at DESC LIMIT 200
        """)

        # -- IPs (top 100) --
        ips = q("""
            SELECT ip,
                   COUNT(DISTINCT visitor_id) AS visitors,
                   COUNT(DISTINCT session_id) AS sessions,
                   COUNT(*) AS events,
                   COUNT(CASE WHEN event_type='page_view' THEN 1 END) AS pageviews,
                   MIN(created_at) AS first_seen, MAX(created_at) AS last_seen,
                   bool_or(is_bot) AS has_bot,
                   MAX(CASE WHEN is_bot THEN bot_type END) AS bot_type
            FROM analytics_events
            WHERE created_at >= :since
            GROUP BY ip
            ORDER BY events DESC LIMIT 100
        """)

        # -- Visitors (top 100 unique by recency) --
        visitors = q("""
            SELECT visitor_id, ip,
                   MAX(user_agent),
                   MIN(created_at) AS first_seen, MAX(created_at) AS last_seen,
                   COUNT(*) AS events, COUNT(DISTINCT session_id) AS sessions,
                   COUNT(CASE WHEN event_type='page_view' THEN 1 END) AS pageviews,
                   bool_or(is_bot), MAX(CASE WHEN is_bot THEN bot_type END)
            FROM analytics_events
            WHERE created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY visitor_id, ip
            ORDER BY last_seen DESC LIMIT 100
        """)

        # -- Live feed (last 100 events) --
        recent = q("""
            SELECT event_type, visitor_id, ip, page_url, is_bot, bot_type, created_at
            FROM analytics_events
            WHERE created_at >= :since
            ORDER BY created_at DESC LIMIT 100
        """)

        # -- Referrers / Devices / Browsers / OS / Pages --
        referrers = q("""
            SELECT COALESCE(json_extract_path_text(data_json::json,'traffic_source','referrer_domain'),'direct'),
                   COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type='page_view' AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20
        """)
        devices = q("""
            SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','device'),'unknown'),
                   COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type='page_view' AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY 1 ORDER BY 2 DESC
        """)
        browsers = q("""
            SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','browser'),'unknown'),
                   COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type='page_view' AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY 1 ORDER BY 2 DESC
        """)
        oses = q("""
            SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','os'),'unknown'),
                   COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type='page_view' AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY 1 ORDER BY 2 DESC
        """)
        pages = q("""
            SELECT page_url, COUNT(*), COUNT(DISTINCT visitor_id)
            FROM analytics_events
            WHERE event_type='page_view' AND created_at >= :since AND (is_bot = false OR is_bot IS NULL)
            GROUP BY page_url ORDER BY 2 DESC LIMIT 20
        """)

        # -- Quiz answer breakdown (for product insight) --
        quiz_answers = q("""
            SELECT json_extract_path_text(data_json::json,'step_number') AS step,
                   json_extract_path_text(data_json::json,'step_answer') AS answer,
                   COUNT(*) AS n
            FROM analytics_events
            WHERE event_type='quiz_step' AND created_at >= :since
            GROUP BY step, answer
            ORDER BY step ASC, n DESC
        """)

        # -- Revenue by product --
        by_product = q("""
            SELECT product_type, COUNT(*), COALESCE(SUM(amount),0)
            FROM orders
            WHERE status IN ('paid','delivered')
            GROUP BY product_type ORDER BY 3 DESC
        """, {})

        # -- System counts --
        wait_count = q1("SELECT COUNT(*) FROM waitlist", {})
        blog_count = q1("SELECT COUNT(*) FROM blog_posts", {})
        social_count = q1("SELECT COUNT(*) FROM social_posts", {})
        venue_count = q1("SELECT COUNT(*) FROM venues WHERE active", {})
        customer_count = q1("SELECT COUNT(*) FROM customers", {})

        # -- Waitlist signups --
        waitlist_recent = q("""
            SELECT email, source, created_at FROM waitlist
            WHERE created_at >= :since ORDER BY created_at DESC LIMIT 50
        """)

        return {
            "period": period,
            "generated_at": datetime.utcnow().isoformat(),
            "overview": {
                "events": overview[0], "visitors": overview[1],
                "sessions": overview[2], "unique_ips": overview[3],
                "bot_events": bots[0], "bot_ips": bots[1],
            },
            "revenue": {
                "period_paid": float(paid_rev),
                "period_paid_orders": paid_orders,
                "period_pending_orders": pending_orders,
                "period_failed_orders": failed_orders,
                "period_total_orders": total_orders_period,
                "all_time_paid": float(all_rev[0]) if all_rev else 0,
                "all_time_paid_orders": all_rev[1] if all_rev else 0,
                "arpu": round(arpu, 2),
            },
            "funnel": funnel,
            "events_series": [
                {"d": r[0].isoformat() if r[0] else None, "events": r[1], "visitors": r[2]}
                for r in events_series
            ],
            "rev_series": [
                {"d": r[0].isoformat() if r[0] else None, "orders": r[1], "revenue": float(r[2])}
                for r in rev_series
            ],
            "orders": [
                {
                    "id": r[0], "product": r[1], "amount": float(r[2]) if r[2] else 0,
                    "status": r[3], "paypal_id": r[4],
                    "created_at": r[5].isoformat() if r[5] else None,
                    "email": r[6], "name": r[7], "customer_id": r[8],
                } for r in orders
            ],
            "ips": [
                {
                    "ip": r[0], "visitors": r[1], "sessions": r[2], "events": r[3], "pageviews": r[4],
                    "first_seen": r[5].isoformat() if r[5] else None,
                    "last_seen": r[6].isoformat() if r[6] else None,
                    "has_bot": r[7], "bot_type": r[8],
                } for r in ips
            ],
            "visitors": [
                {
                    "visitor_id": (r[0] or "")[:12], "ip": r[1],
                    "ua": (r[2] or "")[:140],
                    "first_seen": r[3].isoformat() if r[3] else None,
                    "last_seen": r[4].isoformat() if r[4] else None,
                    "events": r[5], "sessions": r[6], "pageviews": r[7],
                    "is_bot": r[8], "bot_type": r[9],
                } for r in visitors
            ],
            "recent": [
                {
                    "type": r[0], "visitor": (r[1] or "")[:12], "ip": r[2],
                    "page": r[3], "is_bot": r[4], "bot_type": r[5],
                    "time": r[6].isoformat() if r[6] else None,
                } for r in recent
            ],
            "referrers": [{"referrer": r[0], "visitors": r[1]} for r in referrers],
            "devices": [{"device": r[0], "visitors": r[1]} for r in devices],
            "browsers": [{"browser": r[0], "visitors": r[1]} for r in browsers],
            "os": [{"os": r[0], "visitors": r[1]} for r in oses],
            "pages": [{"url": r[0], "views": r[1], "visitors": r[2]} for r in pages],
            "quiz_answers": [{"step": r[0], "answer": r[1], "count": r[2]} for r in quiz_answers],
            "by_product": [{"product": r[0], "count": r[1], "revenue": float(r[2])} for r in by_product],
            "system": {
                "waitlist": wait_count[0] if wait_count else 0,
                "blog_posts": blog_count[0] if blog_count else 0,
                "social_posts": social_count[0] if social_count else 0,
                "venues_active": venue_count[0] if venue_count else 0,
                "customers": customer_count[0] if customer_count else 0,
            },
            "waitlist_recent": [
                {"email": r[0], "source": r[1], "time": r[2].isoformat() if r[2] else None}
                for r in waitlist_recent
            ],
        }
    except Exception:
        log.exception("admin_data query failed")
        raise HTTPException(status_code=500, detail="dashboard query failed")


@router.get("/api/admin/ip/{ip}")
async def ip_detail(
    ip: str,
    user: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """All events from a single IP, for drill-down."""
    _ensure_analytics_table(db)
    rows = db.execute(text("""
        SELECT event_type, visitor_id, session_id, page_url, user_agent,
               is_bot, bot_type, data_json, created_at
        FROM analytics_events
        WHERE ip = :ip
        ORDER BY created_at DESC LIMIT 500
    """), {"ip": ip}).fetchall()
    summary = db.execute(text("""
        SELECT COUNT(*), COUNT(DISTINCT visitor_id), COUNT(DISTINCT session_id),
               MIN(created_at), MAX(created_at), bool_or(is_bot)
        FROM analytics_events WHERE ip = :ip
    """), {"ip": ip}).fetchone()
    orders = db.execute(text("""
        SELECT o.id, o.product_type, o.amount, o.status, o.created_at, c.email
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        WHERE o.customer_id IN (
            SELECT DISTINCT c.id FROM customers c
            JOIN analytics_events e ON e.data_json::json->>'email' = c.email
            WHERE e.ip = :ip
        )
        ORDER BY o.created_at DESC LIMIT 20
    """), {"ip": ip}).fetchall()
    return {
        "ip": ip,
        "summary": {
            "events": summary[0], "visitors": summary[1], "sessions": summary[2],
            "first_seen": summary[3].isoformat() if summary[3] else None,
            "last_seen": summary[4].isoformat() if summary[4] else None,
            "is_bot": summary[5],
        } if summary else {},
        "events": [
            {
                "type": r[0], "visitor": (r[1] or "")[:12], "session": (r[2] or "")[:8],
                "page": r[3], "ua": (r[4] or "")[:200], "is_bot": r[5], "bot_type": r[6],
                "data": r[7][:500] if r[7] else None,
                "time": r[8].isoformat() if r[8] else None,
            } for r in rows
        ],
        "orders": [
            {"id": r[0], "product": r[1], "amount": float(r[2]) if r[2] else 0,
             "status": r[3], "time": r[4].isoformat() if r[4] else None, "email": r[5]}
            for r in orders
        ],
    }
