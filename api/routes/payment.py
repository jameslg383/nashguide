"""PayPal payment flow: create order → PayPal redirect → capture → enqueue itinerary."""
import json
import logging

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.models.database import get_db
from api.models.order import Order, QuizResponse
from api.services import paypal

log = logging.getLogger("payment")

router = APIRouter(prefix="/api/payment", tags=["payment"])

PRICING = {"classic": 9.99, "vip": 29.99, "bach": 19.99}
PRODUCT_NAMES = {
    "classic": "NashGuide Classic Itinerary",
    "vip": "NashGuide VIP Itinerary",
    "bach": "NashGuide Bachelorette Pack",
}

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)


class CreatePayment(BaseModel):
    customer_id: int
    quiz_response_id: int
    product_type: str


class CapturePayment(BaseModel):
    paypal_order_id: str


# -- Helpers -----------------------------------------------------------------


async def _capture_and_fulfill(paypal_order_id: str, db: Session) -> dict:
    """Capture a PayPal order, mark it paid, and enqueue itinerary generation."""
    order = db.query(Order).filter(Order.paypal_order_id == paypal_order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    try:
        result = await paypal.capture_order(paypal_order_id)
    except Exception as e:
        log.exception("PayPal capture_order failed (paypal_order_id=%s)", paypal_order_id)
        order.status = "failed"
        db.commit()
        raise HTTPException(502, f"Payment capture error: {e}")

    status = result.get("status")
    if status != "COMPLETED":
        order.status = "failed"
        db.commit()
        raise HTTPException(402, f"Payment not completed: {status}")

    order.status = "paid"
    db.commit()

    # Enqueue itinerary generation job — don't fail the request if Redis is down,
    # the admin can re-run from the dashboard.
    try:
        _redis.rpush("nashguide:jobs:itinerary", json.dumps({"order_id": order.id}))
    except Exception:
        log.exception("Failed to enqueue itinerary job (order_id=%s)", order.id)

    return {"order_id": order.id, "status": "paid"}


# -- Routes ------------------------------------------------------------------


@router.post("/create")
async def create_payment(payload: CreatePayment, db: Session = Depends(get_db)):
    """Create a PayPal order and return its approval URL for the frontend to redirect to."""
    if payload.product_type not in PRICING:
        raise HTTPException(400, "Invalid product_type")
    amount = PRICING[payload.product_type]

    order = Order(
        customer_id=payload.customer_id,
        product_type=payload.product_type,
        amount=amount,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Link the quiz response to this order so the planner agent can find it.
    quiz = db.get(QuizResponse, payload.quiz_response_id)
    if quiz:
        quiz.order_id = order.id
        db.commit()

    try:
        pp = await paypal.create_order(
            amount=amount,
            description=PRODUCT_NAMES[payload.product_type],
            return_url=f"{settings.site_url}/api/payment/success",
            cancel_url=f"{settings.site_url}/api/payment/cancel",
        )
    except Exception as e:
        log.exception("PayPal create_order failed (order_id=%s)", order.id)
        order.status = "failed"
        db.commit()
        raise HTTPException(502, f"Payment provider error: {e}")

    order.paypal_order_id = pp["id"]
    db.commit()

    approval_url = next(
        (l["href"] for l in pp.get("links", []) if l.get("rel") == "approve"),
        None,
    )
    if not approval_url:
        log.error("No approval URL in PayPal create response: %s", pp)
        raise HTTPException(502, "No approval URL in PayPal response")

    return {
        "order_id": order.id,
        "paypal_order_id": pp["id"],
        "approval_url": approval_url,
    }


@router.post("/capture")
async def capture_payment(payload: CapturePayment, db: Session = Depends(get_db)):
    """Programmatic capture endpoint (POST). Used by SPA flows that own the PayPal redirect."""
    return await _capture_and_fulfill(str(payload.paypal_order_id), db)


@router.get("/success")
async def payment_success(
    token: str = Query(None),
    PayerID: str = Query(None),
    db: Session = Depends(get_db),
):
    """PayPal redirects here after user approval. The `token` query param is the PayPal order ID."""
    if not token:
        return RedirectResponse(url="/?payment=error")
    try:
        await _capture_and_fulfill(token, db)
    except HTTPException:
        return RedirectResponse(url="/?payment=error")
    except Exception:
        log.exception("payment_success handler crashed (token=%s)", token)
        return RedirectResponse(url="/?payment=error")
    return RedirectResponse(url="/?payment=success")


@router.get("/cancel")
async def payment_cancel():
    """PayPal redirects here if the user cancels out of the approval flow."""
    return RedirectResponse(url="/?payment=cancelled")
