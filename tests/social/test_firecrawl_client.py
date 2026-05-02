"""Smoke test the Firecrawl wrapper without any network or SDK.

We avoid `importlib.reload` here — reloading shared service modules leaves
sibling modules (like the scraper agent) holding stale references and
breaks downstream tests. Instead we mutate the live `settings` instance.
"""
from __future__ import annotations


def test_is_configured_reflects_settings(monkeypatch):
    from api import config
    from api.services import firecrawl_client

    monkeypatch.setattr(config.settings, "FIRECRAWL_API_KEY", "")
    monkeypatch.setattr(firecrawl_client, "_app", None, raising=False)
    assert firecrawl_client.is_configured() is False
    assert firecrawl_client.scrape("https://x.example") is None
    assert firecrawl_client.search("anything") == []


def test_coerce_dict_input():
    from api.services.firecrawl_client import _coerce
    out = _coerce({"data": {"markdown": "hi", "metadata": {"title": "T"}}}, "https://x")
    assert out["url"] == "https://x"
    assert out["markdown"] == "hi"
    assert out["metadata"]["title"] == "T"


def test_coerce_object_input():
    class Stub:
        markdown = "obj-md"
        html = "<p>obj</p>"
        metadata = {"title": "ObjT"}

    from api.services.firecrawl_client import _coerce
    out = _coerce(Stub(), "https://y")
    assert out["url"] == "https://y"
    assert out["markdown"] == "obj-md"
    assert out["html"] == "<p>obj</p>"


def test_coerce_handles_none():
    from api.services.firecrawl_client import _coerce
    assert _coerce(None, "https://z") == {"url": "https://z"}


def test_fetch_page_falls_back_to_httpx(monkeypatch):
    """When Firecrawl isn't configured, fetch_page uses _fetch_httpx + strip."""
    from api import config
    from api.services import firecrawl_client, social_scraper

    monkeypatch.setattr(config.settings, "FIRECRAWL_API_KEY", "")
    monkeypatch.setattr(firecrawl_client, "_app", None, raising=False)
    monkeypatch.setattr(
        social_scraper,
        "_fetch_httpx",
        lambda url: "<html><body>hello world</body></html>",
    )

    body, fetcher = social_scraper.fetch_page("https://x.example")
    assert fetcher == "httpx"
    assert "hello world" in body


def test_fetch_page_uses_firecrawl_when_configured(monkeypatch):
    from api.services import firecrawl_client, social_scraper

    monkeypatch.setattr(firecrawl_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        firecrawl_client,
        "scrape",
        lambda url, **kw: {"url": url, "markdown": "FC content here", "html": None, "metadata": {}},
    )

    body, fetcher = social_scraper.fetch_page("https://x.example")
    assert fetcher == "firecrawl"
    assert "FC content" in body
