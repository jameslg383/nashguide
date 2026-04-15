"""Analytics routes — receives tracker events, serves dashboard."""
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import text
from datetime import datetime, timedelta
from pathlib import Path
import json

from api.models.database import get_db
from api.config import settings

router = APIRouter()


@router.post("/api/analytics/track")
async def track_event(request: Request):
    """Receive analytics events from the tracker script."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    event_type = body.get("event_type", "unknown")
    visitor_id = body.get("visitor_id", "")
    session_id = body.get("session_id", "")

    # Get IP and geo info
    ip = request.headers.get("x-forwarded-for", request.headers.get("x-real-ip", request.client.host))
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    user_agent = request.headers.get("user-agent", "")

    db = next(get_db())
    try:
        db.execute(
            text("""
                INSERT INTO analytics_events
                (event_type, visitor_id, session_id, ip, user_agent, data_json, page_url, created_at)
                VALUES (:event_type, :visitor_id, :session_id, :ip, :user_agent, :data_json, :page_url, :created_at)
            """),
            {
                "event_type": event_type,
                "visitor_id": visitor_id,
                "session_id": session_id,
                "ip": ip,
                "user_agent": user_agent,
                "data_json": json.dumps(body),
                "page_url": body.get("page_url", "/"),
                "created_at": datetime.utcnow()
            }
        )
        db.commit()
    except Exception as e:
        db.rollback()
        # Table might not exist yet, create it
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(100) NOT NULL,
                    visitor_id VARCHAR(100),
                    session_id VARCHAR(100),
                    ip VARCHAR(50),
                    user_agent TEXT,
                    data_json TEXT,
                    page_url VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics_events(event_type);
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics_events(created_at);
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_analytics_visitor ON analytics_events(visitor_id);
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_analytics_session ON analytics_events(session_id);
            """))
            db.commit()
            # Retry insert
            db.execute(
                text("""
                    INSERT INTO analytics_events
                    (event_type, visitor_id, session_id, ip, user_agent, data_json, page_url, created_at)
                    VALUES (:event_type, :visitor_id, :session_id, :ip, :user_agent, :data_json, :page_url, :created_at)
                """),
                {
                    "event_type": event_type,
                    "visitor_id": visitor_id,
                    "session_id": session_id,
                    "ip": ip,
                    "user_agent": user_agent,
                    "data_json": json.dumps(body),
                    "page_url": body.get("page_url", "/"),
                    "created_at": datetime.utcnow()
                }
            )
            db.commit()
        except Exception as e2:
            db.rollback()
            return {"ok": False, "error": str(e2)}
    finally:
        db.close()

    return {"ok": True}


@router.get("/api/analytics/data")
async def analytics_data(
    key: str = Query(...),
    period: str = Query("7d"),
    event_type: str = Query(None)
):
    """Return analytics data as JSON for the dashboard."""
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Parse period
    days = 7
    if period == "24h": days = 1
    elif period == "7d": days = 7
    elif period == "30d": days = 30
    elif period == "90d": days = 90
    elif period == "all": days = 3650

    since = datetime.utcnow() - timedelta(days=days)

    db = next(get_db())
    try:
        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                visitor_id VARCHAR(100),
                session_id VARCHAR(100),
                ip VARCHAR(50),
                user_agent TEXT,
                data_json TEXT,
                page_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()

        # Overview stats
        overview = db.execute(text("""
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT visitor_id) as unique_visitors,
                COUNT(DISTINCT session_id) as total_sessions,
                COUNT(DISTINCT ip) as unique_ips
            FROM analytics_events WHERE created_at >= :since
        """), {"since": since}).fetchone()

        # Events by type
        events_by_type = db.execute(text("""
            SELECT event_type, COUNT(*) as count
            FROM analytics_events WHERE created_at >= :since
            GROUP BY event_type ORDER BY count DESC
        """), {"since": since}).fetchall()

        # Page views over time (by hour for 24h, by day otherwise)
        if days <= 1:
            time_series = db.execute(text("""
                SELECT date_trunc('hour', created_at) as period, COUNT(*) as views,
                       COUNT(DISTINCT visitor_id) as visitors
                FROM analytics_events
                WHERE event_type = 'page_view' AND created_at >= :since
                GROUP BY period ORDER BY period
            """), {"since": since}).fetchall()
        else:
            time_series = db.execute(text("""
                SELECT date_trunc('day', created_at) as period, COUNT(*) as views,
                       COUNT(DISTINCT visitor_id) as visitors
                FROM analytics_events
                WHERE event_type = 'page_view' AND created_at >= :since
                GROUP BY period ORDER BY period
            """), {"since": since}).fetchall()

        # Funnel: page_view -> quiz_start -> quiz_complete -> tier_select -> payment_start -> payment_success
        funnel_steps = ['page_view', 'quiz_start', 'quiz_step', 'quiz_complete', 'tier_view', 'tier_select', 'checkout_start', 'payment_start', 'payment_success']
        funnel = []
        for step in funnel_steps:
            row = db.execute(text("""
                SELECT COUNT(DISTINCT visitor_id) as visitors
                FROM analytics_events WHERE event_type = :et AND created_at >= :since
            """), {"et": step, "since": since}).fetchone()
            funnel.append({"step": step, "visitors": row[0] if row else 0})

        # Top referrers
        referrers = db.execute(text("""
            SELECT
                COALESCE(
                    json_extract_path_text(data_json::json, 'traffic_source', 'referrer_domain'),
                    'unknown'
                ) as referrer,
                COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events
            WHERE event_type = 'page_view' AND created_at >= :since
            GROUP BY referrer ORDER BY visitors DESC LIMIT 20
        """), {"since": since}).fetchall()

        # Devices
        devices = db.execute(text("""
            SELECT
                COALESCE(
                    json_extract_path_text(data_json::json, 'device_info', 'device'),
                    'unknown'
                ) as device,
                COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events
            WHERE event_type = 'page_view' AND created_at >= :since
            GROUP BY device ORDER BY visitors DESC
        """), {"since": since}).fetchall()

        # Browsers
        browsers = db.execute(text("""
            SELECT
                COALESCE(
                    json_extract_path_text(data_json::json, 'device_info', 'browser'),
                    'unknown'
                ) as browser,
                COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events
            WHERE event_type = 'page_view' AND created_at >= :since
            GROUP BY browser ORDER BY visitors DESC
        """), {"since": since}).fetchall()

        # OS
        oses = db.execute(text("""
            SELECT
                COALESCE(
                    json_extract_path_text(data_json::json, 'device_info', 'os'),
                    'unknown'
                ) as os,
                COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events
            WHERE event_type = 'page_view' AND created_at >= :since
            GROUP BY os ORDER BY visitors DESC
        """), {"since": since}).fetchall()

        # Scroll depth distribution
        scroll = db.execute(text("""
            SELECT
                json_extract_path_text(data_json::json, 'depth_pct') as depth,
                COUNT(DISTINCT visitor_id) as visitors
            FROM analytics_events
            WHERE event_type = 'scroll_depth' AND created_at >= :since
            GROUP BY depth ORDER BY depth
        """), {"since": since}).fetchall()

        # Average time on page
        avg_time = db.execute(text("""
            SELECT AVG(CAST(json_extract_path_text(data_json::json, 'time_on_page_seconds') AS FLOAT)) as avg_seconds
            FROM analytics_events
            WHERE event_type = 'page_exit' AND created_at >= :since
        """), {"since": since}).fetchone()

        # Recent events (live feed)
        recent = db.execute(text("""
            SELECT event_type, visitor_id, ip, page_url, data_json, created_at
            FROM analytics_events
            WHERE created_at >= :since
            ORDER BY created_at DESC LIMIT 50
        """), {"since": since}).fetchall()

        # Quiz step breakdown
        quiz_steps = db.execute(text("""
            SELECT
                json_extract_path_text(data_json::json, 'step_number') as step,
                json_extract_path_text(data_json::json, 'step_answer') as answer,
                COUNT(*) as count
            FROM analytics_events
            WHERE event_type = 'quiz_step' AND created_at >= :since
            GROUP BY step, answer ORDER BY step, count DESC
        """), {"since": since}).fetchall()

        # Waitlist signups
        waitlist = db.execute(text("""
            SELECT COUNT(DISTINCT visitor_id) as signups
            FROM analytics_events
            WHERE event_type = 'waitlist_signup' AND created_at >= :since
        """), {"since": since}).fetchone()

        # Top clicked elements
        clicks = db.execute(text("""
            SELECT
                json_extract_path_text(data_json::json, 'element_text') as element,
                COUNT(*) as clicks
            FROM analytics_events
            WHERE event_type = 'click' AND created_at >= :since
            GROUP BY element ORDER BY clicks DESC LIMIT 20
        """), {"since": since}).fetchall()

        return {
            "period": period,
            "overview": {
                "total_events": overview[0],
                "unique_visitors": overview[1],
                "total_sessions": overview[2],
                "unique_ips": overview[3]
            },
            "events_by_type": [{"type": r[0], "count": r[1]} for r in events_by_type],
            "time_series": [{"period": r[0].isoformat() if r[0] else None, "views": r[1], "visitors": r[2]} for r in time_series],
            "funnel": funnel,
            "referrers": [{"referrer": r[0], "visitors": r[1]} for r in referrers],
            "devices": [{"device": r[0], "visitors": r[1]} for r in devices],
            "browsers": [{"browser": r[0], "visitors": r[1]} for r in browsers],
            "os": [{"os": r[0], "visitors": r[1]} for r in oses],
            "scroll_depth": [{"depth": r[0], "visitors": r[1]} for r in scroll],
            "avg_time_on_page": round(avg_time[0], 1) if avg_time and avg_time[0] else 0,
            "recent_events": [{"type": r[0], "visitor": r[1][:8] if r[1] else "", "ip": r[2], "page": r[3], "data": r[4], "time": r[5].isoformat() if r[5] else None} for r in recent],
            "quiz_steps": [{"step": r[0], "answer": r[1], "count": r[2]} for r in quiz_steps],
            "waitlist_signups": waitlist[0] if waitlist else 0,
            "top_clicks": [{"element": r[0], "clicks": r[1]} for r in clicks]
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()


@router.get("/admin/analytics", response_class=HTMLResponse)
async def analytics_dashboard(key: str = Query(...)):
    """Serve the analytics dashboard."""
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # api/routes/analytics.py → project_root/static/analytics.html
    dashboard_path = Path(__file__).resolve().parent.parent.parent / "static" / "analytics.html"
    if dashboard_path.exists():
        return FileResponse(str(dashboard_path))
    else:
        return HTMLResponse("<h1>Analytics dashboard not found. Place analytics.html in /static/</h1>")
