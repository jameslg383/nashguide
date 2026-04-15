from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from api.models.database import Base


class AnalyticsEvent(Base):
    """Visitor tracking event. Written by /api/analytics/track, read by the dashboard."""
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    visitor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Single-column indexes for direct lookups
        Index("idx_ae_type", "event_type"),
        Index("idx_ae_created", "created_at"),
        Index("idx_ae_visitor", "visitor_id"),
        Index("idx_ae_session", "session_id"),
        Index("idx_ae_ip", "ip"),
        Index("idx_ae_bot", "is_bot"),
        # Composite — most dashboard queries filter on event_type AND created_at
        Index("idx_ae_type_created", "event_type", "created_at"),
    )
