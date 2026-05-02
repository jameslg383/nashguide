"""Shared fixtures for /social tests.

Each test module gets a fresh in-memory SQLite DB by patching `engine` and
`SessionLocal` before the app imports any routes.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure imports resolve from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    monkeypatch.setenv("NASHGUIDE_ADMIN_KEY", "test-key")


@pytest.fixture
def temp_db(monkeypatch):
    """Hot-swap the global engine/Session to a temp SQLite file DB.

    File-based (not :memory:) so multi-connection access from FastAPI's
    TestClient sees the same data.
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "social_test.db")
    url = f"sqlite:///{db_path}"

    from api.models import database as db_mod

    new_engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    new_session = sessionmaker(bind=new_engine, autocommit=False, autoflush=False, future=True)

    monkeypatch.setattr(db_mod, "engine", new_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", new_session)

    db_mod.init_db()

    # Reset rate limit between tests
    from api.routes import social as social_mod
    social_mod._reset_rate_limit()

    yield new_session

    new_engine.dispose()


@pytest.fixture
def client(temp_db):
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


@pytest.fixture
def db(temp_db):
    s = temp_db()
    try:
        yield s
    finally:
        s.close()
