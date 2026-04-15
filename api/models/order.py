from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    product_type: Mapped[str] = mapped_column(String(64))  # classic | vip | bachelorette
    amount: Mapped[float] = mapped_column(Float)
    paypal_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|paid|delivered|failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuizResponse(Base):
    __tablename__ = "quiz_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    visit_dates: Mapped[str] = mapped_column(String(128))
    num_days: Mapped[int] = mapped_column(Integer)
    group_type: Mapped[str] = mapped_column(String(64))
    vibe: Mapped[str] = mapped_column(String(64))
    budget: Mapped[str] = mapped_column(String(64))
    must_dos: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
