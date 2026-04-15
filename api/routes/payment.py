import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import redis

from api.config import settings
from api.models.database import get_db
from api.models.order import Order, QuizResponse
from api.services import paypal

router = APIRouter(prefix="/api/payment", tags=["payment"])

PRICING = {"classic": 9.99, "vip": 29.99, "bachelorette": 19.99}
PRODUCT_NAMES = {
    "classic": "NashGuide Classic Itinerary",
    "vip": "NashGuide VIP Itinerary",
    "bachelorette": "NashGuide Bachelorette Pack",
}

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)


class CreatePayment(BaseModel):
    customer_id: int
    quiz_response_id: int
    product_type: str


class CapturePayment(BaseModel):
    paypal_order_id: int | str


@router.post("/create")
async def create_payment(payload: CreatePayment, db: Session = Depends(get_db)):
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

    # link quiz response to order
    quiz = db.get(QuizResponse, payload.quiz_response_id)
    if quiz:
        quiz.order_id = order.id
        db.commit()

    pp = await paypal.create_order(
        amount=amount,
        description=PRODUCT_NAMES[payload.product_type],
        return_url=f"{settings.SITE_URL}/payment/success?order_id={order.id}",
        cancel_url=f"{settings.SITE_URL}/payment/cancel?order_id={order.id}",
    )
    order.paypal_order_id = pp["id"]
    db.commit()

    approve_link = next(
        (l["href"] for l in pp.get("links", []) if l.get("rel") == "approve"), None
    )
    return {"order_id": order.id, "paypal_order_id": pp["id"], "approve_url": approve_link}


@router.post("/capture")
async def capture_payment(payload: CapturePayment, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.paypal_order_id == str(payload.paypal_order_id)).first()
    if not order:
        raise HTTPException(404, "Order not found")

    result = await paypal.capture_order(order.paypal_order_id)
    status = result.get("status")
    if status != "COMPLETED":
        order.status = "failed"
        db.commit()
        raise HTTPException(402, f"Payment not completed: {status}")

    order.status = "paid"
    db.commit()

    # enqueue itinerary job
    _redis.rpush("nashguide:jobs:itinerary", json.dumps({"order_id": order.id}))

    return {"order_id": order.id, "status": "paid"}
