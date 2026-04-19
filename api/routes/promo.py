"""Promo code redemption + admin management.

Customer flow: POST /api/promo/apply does the whole quiz-submit → paid-order →
itinerary-enqueue chain in one call when the code is 100% free (MVP only
handles that case). Returns success so the frontend can redirect to the
success view without touching PayPal.

Admin: /api/admin/promo (GET list, POST create, POST deactivate) — session
auth via the admin console.
"""
import json
import logging
from datetime import datetime
from typing import Optional

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from api.config import settings
from api.models.customer import Customer
from api.models.database import get_db
from api.models.order import Order, QuizResponse
from api.models.promo_code import PromoCode
from api.routes.admin_console import require_admin

log = logging.getLogger("promo")

router = APIRouter()

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

PRICING = {"classic": 9.99, "vip": 29.99, "bach": 19.99}


# -- Customer-facing ---------------------------------------------------------


class PromoApply(BaseModel):
    code: str
    email: EmailStr
    name: str | None = None
    visit_dates: str
    num_days: int
    group_type: str
    vibe: str
    budget: str
    must_dos: str | None = None
    product_type: str


def _validate_promo(db: Session, code: str, product_type: str) -> PromoCode:
    """Look up and validate a code. Raises HTTPException on failure."""
    normalized = (code or "").strip().upper()
    if not normalized:
        raise HTTPException(400, "No promo code provided")

    promo = db.query(PromoCode).filter(PromoCode.code == normalized).first()
    if not promo:
        raise HTTPException(404, "Invalid promo code")
    if not promo.active:
        raise HTTPException(400, "This code has been deactivated")
    if promo.valid_until and promo.valid_until < datetime.utcnow():
        raise HTTPException(400, "This code has expired")
    if promo.max_uses is not None and promo.uses_count >= promo.max_uses:
        raise HTTPException(400, "This code has been fully redeemed")
    allowed = promo.allowed_product_types or []
    if allowed and product_type not in allowed:
        raise HTTPException(400, f"This code isn't valid for {product_type}")
    if promo.discount_type != "free":
        # Discount codes not supported in the MVP — the PayPal flow would need
        # to be modified to charge a smaller amount.
        raise HTTPException(501, "Only free codes are supported right now")
    return promo


@router.post("/api/promo/apply")
def apply_promo(payload: PromoApply, db: Session = Depends(get_db)):
    """Redeem a free promo code end-to-end: validate → quiz → paid order → enqueue."""
    if payload.product_type not in PRICING:
        raise HTTPException(400, "Invalid product_type")

    promo = _validate_promo(db, payload.code, payload.product_type)

    # 1. Customer (find or create)
    customer = db.query(Customer).filter(Customer.email == payload.email).first()
    if not customer:
        customer = Customer(email=payload.email, name=payload.name, source="promo")
        db.add(customer)
        db.commit()
        db.refresh(customer)

    # 2. Quiz response
    quiz = QuizResponse(
        visit_dates=payload.visit_dates,
        num_days=payload.num_days,
        group_type=payload.group_type,
        vibe=payload.vibe,
        budget=payload.budget,
        must_dos=payload.must_dos,
        raw_json=payload.model_dump(),
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    # 3. Paid order at $0, tagged with promo code in paypal_order_id slot for traceability
    order = Order(
        customer_id=customer.id,
        product_type=payload.product_type,
        amount=0.0,  # free redemption
        status="paid",
        paypal_order_id=f"PROMO:{promo.code}",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    quiz.order_id = order.id
    promo.uses_count += 1
    db.commit()

    # 4. Enqueue itinerary generation
    try:
        _redis.rpush("nashguide:jobs:itinerary", json.dumps({"order_id": order.id}))
    except Exception:
        log.exception("Failed to enqueue itinerary after promo redemption (order_id=%s)", order.id)

    log.info(
        "Promo redeemed: code=%s order_id=%s customer_id=%s product=%s uses=%s",
        promo.code, order.id, customer.id, payload.product_type, promo.uses_count,
    )

    return {
        "success": True,
        "free": True,
        "order_id": order.id,
        "customer_id": customer.id,
        "quiz_response_id": quiz.id,
        "code": promo.code,
        "uses_remaining": (promo.max_uses - promo.uses_count) if promo.max_uses else None,
        "message": "Code applied — your itinerary is being generated. Check your email shortly.",
    }


@router.get("/api/promo/check/{code}")
def check_promo(code: str, product_type: str = "classic", db: Session = Depends(get_db)):
    """Pre-validate a code without redeeming — lets the frontend give instant
    feedback when the user types a code before clicking Apply."""
    try:
        promo = _validate_promo(db, code, product_type)
    except HTTPException as e:
        return {"valid": False, "reason": e.detail}
    return {
        "valid": True,
        "code": promo.code,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "uses_remaining": (promo.max_uses - promo.uses_count) if promo.max_uses else None,
    }


# -- Admin management --------------------------------------------------------


class PromoCreate(BaseModel):
    code: str
    description: str | None = None
    discount_type: str = "free"
    discount_value: float = 100.0
    max_uses: int | None = None
    valid_until: datetime | None = None
    allowed_product_types: list[str] | None = None


def _serialize(p: PromoCode) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "description": p.description,
        "discount_type": p.discount_type,
        "discount_value": p.discount_value,
        "max_uses": p.max_uses,
        "uses_count": p.uses_count,
        "uses_remaining": (p.max_uses - p.uses_count) if p.max_uses else None,
        "valid_until": p.valid_until.isoformat() if p.valid_until else None,
        "active": p.active,
        "allowed_product_types": p.allowed_product_types or [],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "created_by": p.created_by,
    }


@router.get("/api/admin/promo")
def list_promos(user: str = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()
    return {"codes": [_serialize(p) for p in rows]}


@router.post("/api/admin/promo")
def create_promo(
    payload: PromoCreate,
    user: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized = payload.code.strip().upper()
    if not normalized:
        raise HTTPException(400, "Code is required")
    if db.query(PromoCode).filter(PromoCode.code == normalized).first():
        raise HTTPException(409, f"Code '{normalized}' already exists")
    if payload.discount_type not in ("free", "percent", "amount"):
        raise HTTPException(400, "Invalid discount_type")

    promo = PromoCode(
        code=normalized,
        description=payload.description,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        max_uses=payload.max_uses,
        valid_until=payload.valid_until,
        allowed_product_types=payload.allowed_product_types or [],
        created_by=user,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    log.info("Promo created by %s: %s", user, normalized)
    return _serialize(promo)


@router.post("/api/admin/promo/{code}/deactivate")
def deactivate_promo(
    code: str,
    user: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    promo = db.query(PromoCode).filter(PromoCode.code == code.strip().upper()).first()
    if not promo:
        raise HTTPException(404, "Code not found")
    promo.active = False
    db.commit()
    log.info("Promo deactivated by %s: %s", user, promo.code)
    return _serialize(promo)


@router.post("/api/admin/promo/{code}/activate")
def activate_promo(
    code: str,
    user: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    promo = db.query(PromoCode).filter(PromoCode.code == code.strip().upper()).first()
    if not promo:
        raise HTTPException(404, "Code not found")
    promo.active = True
    db.commit()
    return _serialize(promo)
