"""Tests for /social/now — the live-specials endpoint."""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import patch

import pytest

from api.models.social import HappyHourSpecial, SocialVenue


def _seed_basic(db):
    """Two venues, a Tuesday 4–7pm special, and a never-active special."""
    v1 = SocialVenue(
        slug="bar-one", name="Bar One", venue_type="bar", neighborhood="Broadway",
        price_tier=2, vibe_tags=[], hours_json={},
    )
    v2 = SocialVenue(
        slug="bar-two", name="Bar Two", venue_type="bar", neighborhood="The Gulch",
        price_tier=2, vibe_tags=[], hours_json={},
    )
    db.add_all([v1, v2])
    db.flush()

    db.add_all([
        HappyHourSpecial(
            venue_id=v1.id, title="Tue Happy", days_of_week=[1],
            start_time=time(16, 0), end_time=time(19, 0),
            deal_type="drink", source="manual", active=True,
        ),
        HappyHourSpecial(
            venue_id=v2.id, title="Sun-only Brunch", days_of_week=[6],
            start_time=time(11, 0), end_time=time(14, 0),
            deal_type="food", source="manual", active=True,
        ),
        HappyHourSpecial(
            venue_id=v1.id, title="Inactive", days_of_week=[1],
            start_time=time(16, 0), end_time=time(19, 0),
            deal_type="drink", source="manual", active=False,
        ),
    ])
    db.commit()


# Tuesday Apr 14 2026 17:00 CT = active for "Tue Happy"
TUE_5PM = datetime(2026, 4, 14, 17, 0, 0)
# Tuesday Apr 14 2026 11:00 CT = inactive (before window)
TUE_11AM = datetime(2026, 4, 14, 11, 0, 0)


@patch("api.routes.social._now_local")
def test_now_endpoint_at_tue_5pm_includes_happy(mock_now, client, db):
    _seed_basic(db)
    mock_now.return_value = TUE_5PM
    r = client.get("/social/now")
    assert r.status_code == 200
    data = r.json()
    titles = [s["title"] for s in data["specials"]]
    assert "Tue Happy" in titles
    assert "Sun-only Brunch" not in titles
    assert "Inactive" not in titles


@patch("api.routes.social._now_local")
def test_now_endpoint_at_tue_11am_excludes_happy(mock_now, client, db):
    _seed_basic(db)
    mock_now.return_value = TUE_11AM
    r = client.get("/social/now")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["specials"] == []
