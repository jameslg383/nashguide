import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import io
import csv

from api.config import settings
from api.models.database import get_db
from api.models.order import Order
from api.models.customer import Customer
from api.models.venue import Venue
from api.models.content import BlogPost, SocialPost

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(key: str = Query(...)):
    if key != settings.admin_key:
        raise HTTPException(401, "Invalid admin key")
    return True


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    total_orders = db.query(func.count(Order.id)).scalar() or 0
    paid_orders = db.query(func.count(Order.id)).filter(Order.status.in_(["paid", "delivered"])).scalar() or 0
    revenue = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.status.in_(["paid", "delivered"])).scalar() or 0
    customers = db.query(func.count(Customer.id)).scalar() or 0
    conv = (paid_orders / total_orders * 100) if total_orders else 0
    return f"""<!doctype html><html><body style='font-family:system-ui;max-width:900px;margin:40px auto'>
    <h1>NashGuide Admin</h1>
    <ul>
      <li>Customers: <b>{customers}</b></li>
      <li>Orders: <b>{total_orders}</b></li>
      <li>Paid: <b>{paid_orders}</b></li>
      <li>Revenue: <b>${revenue:.2f}</b></li>
      <li>Conversion: <b>{conv:.1f}%</b></li>
    </ul>
    <p><a href='/admin/orders?key={settings.admin_key}'>Orders</a> |
       <a href='/admin/venues?key={settings.admin_key}'>Venues</a> |
       <a href='/admin/content?key={settings.admin_key}'>Content</a> |
       <a href='/admin/orders.csv?key={settings.admin_key}'>Export CSV</a></p>
    </body></html>"""


@router.get("/orders", response_class=HTMLResponse)
def orders_list(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Order).order_by(Order.created_at.desc()).limit(200).all()
    trs = "".join(
        f"<tr><td>{o.id}</td><td>{o.customer_id}</td><td>{o.product_type}</td>"
        f"<td>${o.amount:.2f}</td><td>{o.status}</td><td>{o.created_at:%Y-%m-%d %H:%M}</td></tr>"
        for o in rows
    )
    return f"""<!doctype html><html><body style='font-family:system-ui'><h1>Orders</h1>
    <table border=1 cellpadding=6><tr><th>ID</th><th>Cust</th><th>Type</th><th>$</th><th>Status</th><th>When</th></tr>{trs}</table></body></html>"""


@router.get("/orders.csv")
def orders_csv(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "customer_id", "product_type", "amount", "status", "created_at"])
    for o in db.query(Order).all():
        w.writerow([o.id, o.customer_id, o.product_type, o.amount, o.status, o.created_at.isoformat()])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=orders.csv"})


@router.get("/venues", response_class=HTMLResponse)
def venues_list(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(Venue).order_by(Venue.category, Venue.name).all()
    trs = "".join(
        f"<tr><td>{v.id}</td><td>{v.name}</td><td>{v.category}</td><td>{v.neighborhood}</td>"
        f"<td>{'$' * v.price_level}</td><td>{'✔' if v.active else '—'}</td></tr>"
        for v in rows
    )
    return f"""<!doctype html><html><body style='font-family:system-ui'><h1>Venues ({len(rows)})</h1>
    <table border=1 cellpadding=6><tr><th>ID</th><th>Name</th><th>Category</th><th>Hood</th><th>$$</th><th>Active</th></tr>{trs}</table></body></html>"""


@router.post("/venues/seed")
def venues_seed(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    seed_path = Path(__file__).resolve().parent.parent.parent / "data" / "venues_seed.json"
    if not seed_path.exists():
        raise HTTPException(404, "Seed file missing")
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    added = 0
    for row in data:
        if db.query(Venue).filter(Venue.name == row["name"]).first():
            continue
        db.add(Venue(**row))
        added += 1
    db.commit()
    return {"added": added, "total_in_seed": len(data)}


@router.get("/content", response_class=HTMLResponse)
def content_list(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    blogs = db.query(BlogPost).order_by(BlogPost.created_at.desc()).limit(50).all()
    socials = db.query(SocialPost).order_by(SocialPost.created_at.desc()).limit(50).all()
    blog_rows = "".join(f"<li>[{p.status}] {p.title}</li>" for p in blogs)
    social_rows = "".join(f"<li>[{p.status}] {p.content[:100]}</li>" for p in socials)
    return f"""<!doctype html><html><body style='font-family:system-ui'>
    <h1>Content</h1><h2>Blog</h2><ul>{blog_rows or '<li>none</li>'}</ul>
    <h2>Social</h2><ul>{social_rows or '<li>none</li>'}</ul></body></html>"""
