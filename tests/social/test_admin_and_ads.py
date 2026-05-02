"""Admin auth + ad-click tracking."""
from __future__ import annotations

from api.models.social import AdPlacement


ADMIN_PATHS = [
    "/admin/social",
    "/admin/social/submissions",
    "/admin/social/venues",
    "/admin/social/specials",
    "/admin/social/ads",
    "/admin/social/scrape",
]


def test_admin_paths_reject_without_key(client):
    for p in ADMIN_PATHS:
        r = client.get(p)
        assert r.status_code == 401, f"{p} did not require key"


def test_admin_paths_reject_wrong_key(client):
    for p in ADMIN_PATHS:
        r = client.get(p, params={"key": "WRONG"})
        assert r.status_code == 401, f"{p} accepted bad key"


def test_admin_paths_accept_correct_key(client):
    for p in ADMIN_PATHS:
        r = client.get(p, params={"key": "test-key"})
        assert r.status_code == 200, f"{p} rejected correct key (status={r.status_code})"


def test_ad_click_increments_and_redirects(client, db):
    ad = AdPlacement(
        advertiser_name="Acme", placement_slot="homepage_banner",
        click_url="https://example.com/landing", active=True, impressions=0, clicks=0,
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)

    r = client.get(f"/social/ad/{ad.id}/click", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/landing"

    db.refresh(ad)
    assert ad.clicks == 1


def test_ad_click_404_for_missing_ad(client):
    r = client.get("/social/ad/9999/click", follow_redirects=False)
    assert r.status_code == 404
