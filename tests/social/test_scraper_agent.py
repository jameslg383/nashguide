"""Tests for the Firecrawl-driven social scraper agent.

We monkeypatch both `fetch_page` (so no real HTTP) and `extract_from_text`
(so no real LLM). The agent's job is to orchestrate: fetch → extract →
queue submission → record status. That orchestration is what we test.
"""
from __future__ import annotations

from unittest.mock import patch

from api.models.social import ScrapeSource, UserSubmission


def _make_source(db, url="https://example.com/hh", source_type="venue_page",
                 frequency="manual", active=True):
    s = ScrapeSource(url=url, source_type=source_type, frequency=frequency, active=active)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@patch("api.services.social_scraper.extract_from_text")
@patch("api.services.social_scraper.fetch_page")
def test_run_source_persists_submission(mock_fetch, mock_extract, db):
    mock_fetch.return_value = ("the page text", "firecrawl")
    mock_extract.return_value = {
        "venue": {"name": "Bar X", "website": "https://example.com/hh"},
        "specials": [
            {"title": "Happy Hour", "days_of_week": [1, 2, 3, 4],
             "start_time": "16:00", "end_time": "19:00",
             "deal_type": "drink", "discount_value": "$5 wells"},
        ],
    }
    src = _make_source(db)

    from agents import social_scraper_agent
    result = social_scraper_agent.run_source(src.id)

    assert result["ok"] is True
    assert result["specials"] == 1
    assert result["fetcher"] == "firecrawl"

    db.refresh(src)
    assert src.last_status == "ok"
    assert src.last_specials_found == 1
    assert src.last_scraped_at is not None
    assert src.last_error is None

    subs = db.query(UserSubmission).all()
    assert len(subs) == 1
    payload = subs[0].payload_json
    assert payload["source_url"] == "https://example.com/hh"
    assert payload["agent"] == "social_scraper_agent"
    assert subs[0].status == "pending"


@patch("api.services.social_scraper.fetch_page")
def test_run_source_records_error_on_failure(mock_fetch, db):
    mock_fetch.side_effect = RuntimeError("upstream timeout")
    src = _make_source(db)

    from agents import social_scraper_agent
    result = social_scraper_agent.run_source(src.id)

    assert result["ok"] is False
    assert "upstream timeout" in result["error"]

    db.refresh(src)
    assert src.last_status == "error"
    assert "upstream timeout" in (src.last_error or "")
    assert db.query(UserSubmission).count() == 0


def test_run_source_handles_missing_id(db):
    from agents import social_scraper_agent
    result = social_scraper_agent.run_source(99999)
    assert result == {"ok": False, "error": "source not found"}


@patch("api.services.social_scraper.extract_from_text")
@patch("api.services.social_scraper.fetch_page")
def test_listing_page_uses_listing_hint(mock_fetch, mock_extract, db, monkeypatch):
    mock_fetch.return_value = ("listing text", "firecrawl")
    mock_extract.return_value = {"venue": {}, "specials": []}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    src = _make_source(db, source_type="listing_page")

    from agents import social_scraper_agent
    social_scraper_agent.run_source(src.id)

    # extract_from_text was called with hint!=None for listing pages
    _, kwargs = mock_extract.call_args
    assert kwargs.get("hint") is not None
    assert "roundup" in kwargs["hint"].lower() or "listing" in kwargs["hint"].lower()


def test_admin_can_add_and_delete_source(client, db):
    r = client.post(
        "/admin/social/scrape/sources/add",
        params={"key": "test-key"},
        data={"url": "https://test.example/hh", "label": "Test", "source_type": "venue_page",
              "frequency": "weekly"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    sources = db.query(ScrapeSource).all()
    assert len(sources) == 1
    assert sources[0].url == "https://test.example/hh"

    sid = sources[0].id
    r = client.post(
        f"/admin/social/scrape/sources/{sid}/delete",
        params={"key": "test-key"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.query(ScrapeSource).count() == 0


def test_admin_add_source_dedups(client, db):
    payload = {"url": "https://dup.example/hh", "source_type": "venue_page", "frequency": "weekly"}
    r1 = client.post("/admin/social/scrape/sources/add", params={"key": "test-key"}, data=payload, follow_redirects=False)
    r2 = client.post("/admin/social/scrape/sources/add", params={"key": "test-key"}, data=payload, follow_redirects=False)
    assert r1.status_code == 303
    assert r2.status_code == 303
    assert "dup=1" in r2.headers.get("location", "")
    assert db.query(ScrapeSource).count() == 1
