from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from api.models.database import Base


class PromoCode(Base):
    """A redeemable promo/discount code.

    MVP only handles discount_type='free' (100% off, skip PayPal).
    Schema supports 'percent' and 'amount' for future expansion.
    """
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 'free' | 'percent' | 'amount'
    discount_type: Mapped[str] = mapped_column(String(32), default="free")
    # For 'free': always 100 (semantic marker).
    # For 'percent': 5–100.
    # For 'amount': dollars off.
    discount_value: Mapped[float] = mapped_column(Float, default=100.0)

    # null = unlimited
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)

    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Empty list / null = applies to all product_types.
    allowed_product_types: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
