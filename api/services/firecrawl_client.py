"""Thin Firecrawl wrapper.

Why a wrapper? The `firecrawl-py` SDK ships across multiple breaking versions
(0.x, 1.x), and we want one place to deal with that, plus a clean
"if no API key configured, return None" path so the rest of the code can
gracefully fall back to httpx.

Usage:
    from api.services.firecrawl_client import scrape, search, is_configured

    if is_configured():
        page = scrape("https://venue.example/happy-hour")
        # page = {"url": ..., "markdown": ..., "html": ..., "metadata": {...}}
"""
from __future__ import annotations

import logging
from typing import Any

from api.config import settings

log = logging.getLogger("firecrawl")

_app: Any | None = None


def is_configured() -> bool:
    return bool(settings.FIRECRAWL_API_KEY)


def _client():
    """Build (and cache) a FirecrawlApp. Returns None if not configured."""
    global _app
    if _app is not None:
        return _app
    if not is_configured():
        return None
    try:
        from firecrawl import FirecrawlApp  # type: ignore
    except ImportError:
        log.warning("firecrawl-py is not installed; install it to enable scraping.")
        return None
    kwargs: dict[str, Any] = {"api_key": settings.FIRECRAWL_API_KEY}
    if settings.FIRECRAWL_BASE_URL:
        kwargs["api_url"] = settings.FIRECRAWL_BASE_URL
    _app = FirecrawlApp(**kwargs)
    return _app


def _coerce(result: Any, url: str) -> dict[str, Any]:
    """Normalize SDK output across firecrawl-py 0.x / 1.x.

    0.x returned a dict directly. 1.x sometimes wraps in {"data": {...}} and
    sometimes returns an object with attributes. We just want
    {url, markdown, html, metadata} as a plain dict.
    """
    if result is None:
        return {"url": url}
    if isinstance(result, dict):
        data = result.get("data", result)
        return {
            "url": url,
            "markdown": data.get("markdown") or data.get("content"),
            "html": data.get("html") or data.get("rawHtml"),
            "metadata": data.get("metadata") or {},
        }
    # object-style (newer SDK)
    return {
        "url": url,
        "markdown": getattr(result, "markdown", None) or getattr(result, "content", None),
        "html": getattr(result, "html", None) or getattr(result, "raw_html", None),
        "metadata": getattr(result, "metadata", {}) or {},
    }


def scrape(url: str, *, formats: list[str] | None = None) -> dict[str, Any] | None:
    """Fetch a single URL via Firecrawl. Returns None if not configured."""
    app = _client()
    if app is None:
        return None
    fmt = formats or ["markdown"]
    log.info("firecrawl.scrape url=%s formats=%s", url, fmt)
    try:
        # SDK 1.x signature
        result = app.scrape_url(url, params={"formats": fmt})
    except TypeError:
        # SDK 0.x signature (positional only)
        result = app.scrape_url(url)
    return _coerce(result, url)


def search(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Use Firecrawl's search to find candidate URLs (e.g. 'best happy hour
    Nashville Gulch'). Returns [] if not configured or unsupported.
    """
    app = _client()
    if app is None:
        return []
    log.info("firecrawl.search q=%r limit=%d", query, limit)
    try:
        result = app.search(query, params={"limit": limit})
    except (AttributeError, TypeError):
        return []
    if isinstance(result, dict):
        items = result.get("data") or result.get("results") or []
    else:
        items = list(result) if result else []
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append({
                "url": it.get("url") or it.get("link"),
                "title": it.get("title"),
                "description": it.get("description") or it.get("snippet"),
            })
    return out
