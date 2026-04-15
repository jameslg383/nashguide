"""Analytics routes — full visitor intelligence, bot detection, sales tracking."""
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import text
from datetime import datetime, timedelta
from pathlib import Path
import json
import re

from api.models.database import get_db
from api.config import settings

router = APIRouter()

# Known bot patterns
BOT_PATTERNS = [
    r'bot', r'crawl', r'spider', r'slurp', r'mediapartners', r'Googlebot',
    r'Bingbot', r'Baiduspider', r'YandexBot', r'DuckDuckBot', r'facebookexternalhit',
    r'Twitterbot', r'LinkedInBot', r'WhatsApp', r'Slack', r'Discordbot',
    r'Applebot', r'AhrefsBot', r'SemrushBot', r'MJ12bot', r'DotBot',
    r'PetalBot', r'Bytespider', r'GPTBot', r'CCBot', r'ClaudeBot',
    r'anthropic', r'ChatGPT', r'Scrapy', r'curl', r'wget', r'python-requests',
    r'httpx', r'Go-http-client', r'Java/', r'Apache-HttpClient',
    r'HeadlessChrome', r'PhantomJS', r'Selenium', r'Puppeteer',
    r'lighthouse', r'PageSpeed', r'GTmetrix', r'pingdom', r'uptime',
    r'monitoring', r'check_http', r'StatusCake', r'UptimeRobot',
    r'DataForSeoBot', r'serpstat', r'Screaming Frog', r'Netcraft',
    r'archive\.org', r'ia_archiver', r'Nutch'
]
BOT_RE = re.compile('|'.join(BOT_PATTERNS), re.IGNORECASE)


def is_bot(user_agent):
    if not user_agent:
        return True
    return bool(BOT_RE.search(user_agent))


def detect_bot_type(user_agent):
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if any(x in ua for x in ['googlebot', 'google']):
        return 'Google'
    if any(x in ua for x in ['bingbot', 'bing']):
        return 'Bing'
    if 'yandex' in ua:
        return 'Yandex'
    if 'baidu' in ua:
        return 'Baidu'
    if any(x in ua for x in ['facebook', 'facebookexternalhit']):
        return 'Facebook'
    if 'twitter' in ua:
        return 'Twitter'
    if 'linkedin' in ua:
        return 'LinkedIn'
    if any(x in ua for x in ['ahrefs', 'semrush', 'mj12', 'dotbot', 'serpstat']):
        return 'SEO Crawler'
    if any(x in ua for x in ['gptbot', 'ccbot', 'claudebot', 'anthropic', 'chatgpt']):
        return 'AI Bot'
    if any(x in ua for x in ['curl', 'wget', 'python', 'httpx', 'go-http', 'java', 'apache']):
        return 'Script/Library'
    if any(x in ua for x in ['headless', 'phantom', 'selenium', 'puppeteer']):
        return 'Headless Browser'
    if any(x in ua for x in ['lighthouse', 'pagespeed', 'gtmetrix', 'pingdom', 'uptime', 'monitor']):
        return 'Monitoring'
    return 'Other Bot'


ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analytics_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    visitor_id VARCHAR(100),
    session_id VARCHAR(100),
    ip VARCHAR(50),
    user_agent TEXT,
    data_json TEXT,
    page_url VARCHAR(500),
    is_bot BOOLEAN DEFAULT FALSE,
    bot_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ae_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ae_created ON analytics_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ae_visitor ON analytics_events(visitor_id);
CREATE INDEX IF NOT EXISTS idx_ae_session ON analytics_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ae_ip ON analytics_events(ip);
CREATE INDEX IF NOT EXISTS idx_ae_bot ON analytics_events(is_bot);
"""


def ensure_table(db):
    try:
        db.execute(text("SELECT 1 FROM analytics_events LIMIT 1"))
    except Exception:
        db.rollback()
        for stmt in ENSURE_TABLE_SQL.strip().split(';'):
            stmt = stmt.strip()
            if stmt:
                db.execute(text(stmt))
        db.commit()
    # Ensure bot columns exist
    try:
        db.execute(text("SELECT is_bot FROM analytics_events LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            db.execute(text("ALTER TABLE analytics_events ADD COLUMN is_bot BOOLEAN DEFAULT FALSE"))
            db.execute(text("ALTER TABLE analytics_events ADD COLUMN bot_type VARCHAR(50)"))
            db.commit()
        except Exception:
            db.rollback()


@router.post("/api/analytics/track")
async def track_event(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    event_type = body.get("event_type", "unknown")
    visitor_id = body.get("visitor_id", "")
    session_id = body.get("session_id", "")

    ip = request.headers.get("x-forwarded-for", request.headers.get("x-real-ip", ""))
    if not ip:
        ip = request.client.host if request.client else ""
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    user_agent = request.headers.get("user-agent", "")
    bot = is_bot(user_agent)
    bot_type = detect_bot_type(user_agent) if bot else None

    # Inject request headers into data
    body["_headers"] = {
        "accept-language": request.headers.get("accept-language", ""),
        "accept-encoding": request.headers.get("accept-encoding", ""),
        "sec-ch-ua": request.headers.get("sec-ch-ua", ""),
        "sec-ch-ua-platform": request.headers.get("sec-ch-ua-platform", ""),
        "sec-ch-ua-mobile": request.headers.get("sec-ch-ua-mobile", ""),
        "sec-fetch-dest": request.headers.get("sec-fetch-dest", ""),
        "sec-fetch-mode": request.headers.get("sec-fetch-mode", ""),
        "sec-fetch-site": request.headers.get("sec-fetch-site", ""),
        "dnt": request.headers.get("dnt", ""),
        "referer": request.headers.get("referer", ""),
    }

    db = next(get_db())
    try:
        ensure_table(db)
        db.execute(
            text("""
                INSERT INTO analytics_events 
                (event_type, visitor_id, session_id, ip, user_agent, data_json, page_url, is_bot, bot_type, created_at)
                VALUES (:et, :vid, :sid, :ip, :ua, :dj, :pu, :ib, :bt, :ca)
            """),
            {"et": event_type, "vid": visitor_id, "sid": session_id, "ip": ip,
             "ua": user_agent, "dj": json.dumps(body), "pu": body.get("page_url", "/"),
             "ib": bot, "bt": bot_type, "ca": datetime.utcnow()}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        db.close()

    return {"ok": True}


@router.get("/api/analytics/data")
async def analytics_data(
    key: str = Query(...),
    period: str = Query("7d"),
    include_bots: str = Query("false")
):
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}
    days = days_map.get(period, 7)
    since = datetime.utcnow() - timedelta(days=days)
    show_bots = include_bots.lower() == "true"
    bot_filter = "" if show_bots else "AND (is_bot = false OR is_bot IS NULL)"

    db = next(get_db())
    try:
        ensure_table(db)

        def q(sql, params=None):
            params = params or {}
            params["since"] = since
            return db.execute(text(sql), params).fetchall()

        def q1(sql, params=None):
            params = params or {}
            params["since"] = since
            return db.execute(text(sql), params).fetchone()

        # Overview
        o = q1(f"SELECT COUNT(*), COUNT(DISTINCT visitor_id), COUNT(DISTINCT session_id), COUNT(DISTINCT ip) FROM analytics_events WHERE created_at >= :since {bot_filter}")

        # Bot stats (always show)
        bots = q1("SELECT COUNT(*), COUNT(DISTINCT ip) FROM analytics_events WHERE created_at >= :since AND is_bot = true")
        bot_types = q(f"SELECT COALESCE(bot_type,'unknown'), COUNT(*), COUNT(DISTINCT ip) FROM analytics_events WHERE created_at >= :since AND is_bot = true GROUP BY bot_type ORDER BY COUNT(*) DESC")

        # Events by type
        events_by_type = q(f"SELECT event_type, COUNT(*) FROM analytics_events WHERE created_at >= :since {bot_filter} GROUP BY event_type ORDER BY COUNT(*) DESC")

        # Time series
        trunc = 'hour' if days <= 1 else 'day'
        ts = q(f"SELECT date_trunc('{trunc}', created_at), COUNT(*), COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter} GROUP BY 1 ORDER BY 1")

        # Funnel
        funnel_steps = ['page_view','quiz_start','quiz_step','quiz_complete','tier_view','tier_select','checkout_start','payment_start','payment_success']
        funnel = []
        for step in funnel_steps:
            r = q1(f"SELECT COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type=:et AND created_at >= :since {bot_filter}", {"et": step})
            funnel.append({"step": step, "visitors": r[0] if r else 0})

        # Referrers
        referrers = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'traffic_source','referrer_domain'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20""")

        # Devices
        devices = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','device'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC""")

        # Browsers
        browsers = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','browser'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC""")

        # OS
        oses = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','os'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC""")

        # Scroll depth
        scroll = q(f"""SELECT json_extract_path_text(data_json::json,'depth_pct'), COUNT(DISTINCT visitor_id)
            FROM analytics_events WHERE event_type='scroll_depth' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 1""")

        # Avg time
        avg_time = q1(f"""SELECT AVG(CAST(json_extract_path_text(data_json::json,'time_on_page_seconds') AS FLOAT))
            FROM analytics_events WHERE event_type='page_exit' AND created_at >= :since {bot_filter}""")

        # Clicks
        clicks = q(f"""SELECT json_extract_path_text(data_json::json,'element_text'), COUNT(*)
            FROM analytics_events WHERE event_type='click' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20""")

        # Quiz steps
        quiz_steps = q(f"""SELECT json_extract_path_text(data_json::json,'step_number'),
            json_extract_path_text(data_json::json,'step_answer'), COUNT(*)
            FROM analytics_events WHERE event_type='quiz_step' AND created_at >= :since {bot_filter}
            GROUP BY 1,2 ORDER BY 1, 3 DESC""")

        # Waitlist
        waitlist = q1(f"SELECT COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='waitlist_signup' AND created_at >= :since {bot_filter}")

        # Full visitor details — IP, UA, device, location, pages, events
        visitors = q(f"""SELECT visitor_id, ip, user_agent,
            MIN(created_at) as first_seen, MAX(created_at) as last_seen,
            COUNT(*) as total_events,
            COUNT(DISTINCT session_id) as sessions,
            COUNT(CASE WHEN event_type='page_view' THEN 1 END) as pageviews,
            is_bot, bot_type
            FROM analytics_events WHERE created_at >= :since {bot_filter}
            GROUP BY visitor_id, ip, user_agent, is_bot, bot_type
            ORDER BY last_seen DESC LIMIT 200""")

        # IP detail table with all IPs
        ips = q(f"""SELECT ip, 
            COUNT(DISTINCT visitor_id) as visitors,
            COUNT(DISTINCT session_id) as sessions,
            COUNT(*) as events,
            COUNT(CASE WHEN event_type='page_view' THEN 1 END) as pageviews,
            MIN(created_at) as first_seen, MAX(created_at) as last_seen,
            bool_or(is_bot) as has_bot
            FROM analytics_events WHERE created_at >= :since {bot_filter}
            GROUP BY ip ORDER BY events DESC LIMIT 100""")

        # Recent events with full detail
        recent = q(f"""SELECT event_type, visitor_id, session_id, ip, user_agent, page_url, data_json, is_bot, bot_type, created_at
            FROM analytics_events WHERE created_at >= :since {bot_filter}
            ORDER BY created_at DESC LIMIT 100""")

        # Unique pages
        pages = q(f"""SELECT page_url, COUNT(*) as views, COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY page_url ORDER BY views DESC LIMIT 30""")

        # Timezones
        timezones = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','timezone'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20""")

        # Languages
        languages = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','language'),'unknown'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20""")

        # Screen sizes
        screens = q(f"""SELECT COALESCE(json_extract_path_text(data_json::json,'device_info','screen_width'),'?') || 'x' || COALESCE(json_extract_path_text(data_json::json,'device_info','screen_height'),'?'),
            COUNT(DISTINCT visitor_id) FROM analytics_events WHERE event_type='page_view' AND created_at >= :since {bot_filter}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15""")

        # Performance avg
        perf = q1(f"""SELECT AVG(CAST(json_extract_path_text(data_json::json,'ttfb_ms') AS FLOAT)),
            AVG(CAST(json_extract_path_text(data_json::json,'dom_load_ms') AS FLOAT)),
            AVG(CAST(json_extract_path_text(data_json::json,'full_load_ms') AS FLOAT))
            FROM analytics_events WHERE event_type='performance' AND created_at >= :since {bot_filter}""")

        return {
            "period": period, "include_bots": show_bots,
            "overview": {"total_events": o[0], "unique_visitors": o[1], "total_sessions": o[2], "unique_ips": o[3]},
            "bots": {"total_events": bots[0] if bots else 0, "unique_ips": bots[1] if bots else 0,
                     "types": [{"type": r[0], "events": r[1], "ips": r[2]} for r in bot_types]},
            "events_by_type": [{"type": r[0], "count": r[1]} for r in events_by_type],
            "time_series": [{"period": r[0].isoformat() if r[0] else None, "views": r[1], "visitors": r[2]} for r in ts],
            "funnel": funnel,
            "referrers": [{"referrer": r[0], "visitors": r[1]} for r in referrers],
            "devices": [{"device": r[0], "visitors": r[1]} for r in devices],
            "browsers": [{"browser": r[0], "visitors": r[1]} for r in browsers],
            "os": [{"os": r[0], "visitors": r[1]} for r in oses],
            "scroll_depth": [{"depth": r[0], "visitors": r[1]} for r in scroll],
            "avg_time_on_page": round(avg_time[0], 1) if avg_time and avg_time[0] else 0,
            "top_clicks": [{"element": r[0], "clicks": r[1]} for r in clicks],
            "quiz_steps": [{"step": r[0], "answer": r[1], "count": r[2]} for r in quiz_steps],
            "waitlist_signups": waitlist[0] if waitlist else 0,
            "visitors": [{"id": r[0][:12] if r[0] else "", "ip": r[1], "ua": r[2][:120] if r[2] else "",
                         "first_seen": r[3].isoformat() if r[3] else None, "last_seen": r[4].isoformat() if r[4] else None,
                         "events": r[5], "sessions": r[6], "pageviews": r[7],
                         "is_bot": r[8], "bot_type": r[9]} for r in visitors],
            "ips": [{"ip": r[0], "visitors": r[1], "sessions": r[2], "events": r[3], "pageviews": r[4],
                    "first_seen": r[5].isoformat() if r[5] else None, "last_seen": r[6].isoformat() if r[6] else None,
                    "has_bot": r[7]} for r in ips],
            "recent_events": [{"type": r[0], "visitor": r[1][:12] if r[1] else "", "session": r[2][:8] if r[2] else "",
                              "ip": r[3], "ua": r[4][:100] if r[4] else "", "page": r[5],
                              "data": r[6], "is_bot": r[7], "bot_type": r[8],
                              "time": r[9].isoformat() if r[9] else None} for r in recent],
            "pages": [{"url": r[0], "views": r[1], "visitors": r[2]} for r in pages],
            "timezones": [{"tz": r[0], "visitors": r[1]} for r in timezones],
            "languages": [{"lang": r[0], "visitors": r[1]} for r in languages],
            "screens": [{"size": r[0], "visitors": r[1]} for r in screens],
            "performance": {"ttfb": round(perf[0],0) if perf and perf[0] else 0,
                           "dom_load": round(perf[1],0) if perf and perf[1] else 0,
                           "full_load": round(perf[2],0) if perf and perf[2] else 0} if perf else {}
        }
    except Exception as e:
        return {"error": str(e), "detail": "Query failed"}
    finally:
        db.close()


@router.get("/api/analytics/sales")
async def sales_data(key: str = Query(...), period: str = Query("all")):
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    days_map = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}
    days = days_map.get(period, 3650)
    since = datetime.utcnow() - timedelta(days=days)

    db = next(get_db())
    try:
        # Try orders table
        try:
            orders = db.execute(text("""
                SELECT o.id, o.customer_id, o.product_type, o.amount, o.paypal_order_id, o.status, o.created_at,
                       c.email, c.name
                FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.created_at >= :since ORDER BY o.created_at DESC
            """), {"since": since}).fetchall()

            total_rev = db.execute(text("""
                SELECT COALESCE(SUM(amount),0), COUNT(*) FROM orders WHERE status='completed' AND created_at >= :since
            """), {"since": since}).fetchone()

            by_product = db.execute(text("""
                SELECT product_type, COUNT(*), COALESCE(SUM(amount),0) FROM orders WHERE status='completed' AND created_at >= :since
                GROUP BY product_type ORDER BY SUM(amount) DESC
            """), {"since": since}).fetchall()

            by_day = db.execute(text("""
                SELECT date_trunc('day', created_at), COUNT(*), COALESCE(SUM(amount),0)
                FROM orders WHERE status='completed' AND created_at >= :since
                GROUP BY 1 ORDER BY 1
            """), {"since": since}).fetchall()

            by_status = db.execute(text("""
                SELECT status, COUNT(*), COALESCE(SUM(amount),0) FROM orders WHERE created_at >= :since
                GROUP BY status ORDER BY COUNT(*) DESC
            """), {"since": since}).fetchall()

            return {
                "orders": [{"id": r[0], "customer_id": r[1], "product": r[2], "amount": float(r[3]) if r[3] else 0,
                           "paypal_id": r[4], "status": r[5],
                           "date": r[6].isoformat() if r[6] else None,
                           "email": r[7], "name": r[8]} for r in orders],
                "total_revenue": float(total_rev[0]) if total_rev else 0,
                "total_orders": total_rev[1] if total_rev else 0,
                "by_product": [{"product": r[0], "count": r[1], "revenue": float(r[2])} for r in by_product],
                "by_day": [{"date": r[0].isoformat() if r[0] else None, "orders": r[1], "revenue": float(r[2])} for r in by_day],
                "by_status": [{"status": r[0], "count": r[1], "amount": float(r[2])} for r in by_status]
            }
        except Exception as e:
            return {"orders": [], "total_revenue": 0, "total_orders": 0, "by_product": [], "by_day": [], "by_status": [], "note": str(e)}
    finally:
        db.close()


@router.get("/admin/analytics", response_class=HTMLResponse)
async def analytics_dashboard(key: str = Query(...)):
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    # api/routes/analytics.py → project_root/static/analytics.html
    p = Path(__file__).resolve().parent.parent.parent / "static" / "analytics.html"
    if p.exists():
        return FileResponse(str(p))
    return HTMLResponse("<h1>analytics.html not found in /static/</h1>")


@router.get("/admin/sales", response_class=HTMLResponse)
async def sales_dashboard(key: str = Query(...)):
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    # api/routes/analytics.py → project_root/static/sales.html
    p = Path(__file__).resolve().parent.parent.parent / "static" / "sales.html"
    if p.exists():
        return FileResponse(str(p))
    return HTMLResponse("<h1>sales.html not found in /static/</h1>")
