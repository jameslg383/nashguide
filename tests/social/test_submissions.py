"""Tests for the public submission form and rate limiting."""
from __future__ import annotations

import time as _time

from api.models.social import UserSubmission


VALID = {
    "submission_type": "new_venue",
    "name": "Test Bar",
    "neighborhood": "Broadway",
    "venue_type": "bar",
    "loaded_at": "0",  # disables min-time check (=0 means "no value")
}


def _post(client, payload, **headers):
    return client.post("/social/submit", data=payload, headers=headers)


def test_submission_persists_to_db(client, db):
    r = _post(client, VALID)
    assert r.status_code == 200
    rows = db.query(UserSubmission).all()
    assert len(rows) == 1
    assert rows[0].submission_type == "new_venue"
    assert rows[0].payload_json["name"] == "Test Bar"


def test_honeypot_silently_swallows(client, db):
    bad = {**VALID, "website_url": "https://spam.example"}
    r = _post(client, bad)
    assert r.status_code == 200
    assert db.query(UserSubmission).count() == 0


def test_rate_limit_triggers_at_sixth_request(client, db):
    headers = {"x-forwarded-for": "1.2.3.4"}
    for i in range(5):
        r = _post(client, VALID, **headers)
        assert r.status_code == 200, f"request {i+1} should have passed"
    r = _post(client, VALID, **headers)
    assert r.status_code == 429
    # The 5 successful submissions all persisted
    assert db.query(UserSubmission).count() == 5
