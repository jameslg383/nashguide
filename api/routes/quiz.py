from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from api.models.database import get_db
from api.models.customer import Customer
from api.models.order import QuizResponse

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

PRICING = {"classic": 9.99, "vip": 29.99, "bachelorette": 19.99}


class QuizStart(BaseModel):
    email: EmailStr
    name: str | None = None


class QuizSubmit(BaseModel):
    email: EmailStr
    name: str | None = None
    product_type: str = "classic"
    visit_dates: str
    num_days: int
    group_type: str
    vibe: str
    budget: str
    must_dos: str | None = None


@router.post("/start")
def quiz_start(payload: QuizStart, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.email == payload.email).first()
    if not customer:
        customer = Customer(email=payload.email, name=payload.name, source="quiz")
        db.add(customer)
        db.commit()
        db.refresh(customer)
    return {"customer_id": customer.id, "pricing": PRICING}


@router.post("/submit")
def quiz_submit(payload: QuizSubmit, db: Session = Depends(get_db)):
    if payload.product_type not in PRICING:
        raise HTTPException(400, "Invalid product_type")
    customer = db.query(Customer).filter(Customer.email == payload.email).first()
    if not customer:
        customer = Customer(email=payload.email, name=payload.name, source="quiz")
        db.add(customer)
        db.commit()
        db.refresh(customer)

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

    return {
        "quiz_response_id": quiz.id,
        "customer_id": customer.id,
        "product_type": payload.product_type,
        "amount": PRICING[payload.product_type],
    }
