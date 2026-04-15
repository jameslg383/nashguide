"""Smoke test — import everything and check the app boots."""
from fastapi.testclient import TestClient


def test_app_imports():
    from api.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_root():
    from api.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
