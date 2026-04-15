from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.database import Base


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str] = mapped_column(String(255))
    neighborhood: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_level: Mapped[int] = mapped_column(Integer, default=2)  # 1..4
    vibe_tags: Mapped[list] = mapped_column(JSON, default=list)
    best_time: Mapped[str | None] = mapped_column(String(128), nullable=True)
    insider_tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reservation_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    affiliate_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
