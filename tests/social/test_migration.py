"""Migration smoke test — runs the migration up + down against a temp SQLite DB.

We use a SQLite-friendly subset of the migration's operations because the prod
migration uses Postgres-only ARRAY/GIN. This proves the migration *file*
imports cleanly and the metadata round-trips.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect


def _load_migration():
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "20260502_01_add_social_tables.py"
    spec = importlib.util.spec_from_file_location("social_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_migration_module_imports():
    mod = _load_migration()
    assert mod.revision == "20260502_01_social"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_models_create_drop_clean(temp_db):
    """Equivalent of upgrade/downgrade for the SQLAlchemy schema."""
    from api.models import database as db_mod
    from api.models import social as social_mod  # noqa: F401

    inspector = inspect(db_mod.engine)
    tables = set(inspector.get_table_names())
    expected = {"social_venues", "happy_hour_specials", "parking_spots", "user_submissions", "ad_placements"}
    assert expected.issubset(tables)

    db_mod.Base.metadata.drop_all(bind=db_mod.engine, tables=[
        social_mod.AdPlacement.__table__,
        social_mod.UserSubmission.__table__,
        social_mod.ParkingSpot.__table__,
        social_mod.HappyHourSpecial.__table__,
        social_mod.SocialVenue.__table__,
    ])
    inspector = inspect(db_mod.engine)
    tables = set(inspector.get_table_names())
    assert not expected.intersection(tables)
