from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from api.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import all models so metadata sees them
    from api.models import (  # noqa: F401
        customer,
        order,
        venue,
        itinerary,
        content,
        analytics_event,
        promo_code,
    )
    Base.metadata.create_all(bind=engine)
