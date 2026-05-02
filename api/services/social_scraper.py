"""AI-driven happy-hour scraper.

Pipeline: fetch (Firecrawl preferred, httpx fallback) → LLM extraction
(Anthropic) → structured `{venue, specials}` dict. Results never write to
live tables — callers route them through `user_submissions` with
`source='scraped'` for human approval.

Public entry points:
- `scrape_venue(url)` — full pipeline.
- `extract_from_text(url, body, *, hint=None)` — skip the fetch, useful when
  Firecrawl already gave us markdown.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from api.config import settings
from api.services import firecrawl_client
from api.services.claude_ai import client

log = logging.getLogger("social_scraper")


SCRAPE_SYSTEM = """You are a structured-data extractor for Nashville bar/restaurant
happy-hour and special-pricing pages. Given the raw text/HTML of a venue page,
return ONLY JSON describing the venue and any time-based deals you can confirm.
Never invent prices, days, or times. If a field isn't on the page, omit it."""

SCRAPE_SCHEMA = """{
  "venue": {
    "name": "string",
    "address": "string|null",
    "phone": "string|null",
    "website": "string",
    "neighborhood": "string|null"
  },
  "specials": [
    {
      "title": "string",
      "description": "string",
      "days_of_week": [0,1,2,3,4,5,6],
      "start_time": "HH:MM (24h)",
      "end_time":   "HH:MM (24h)",
      "deal_type": "drink|food|both|bogo|flat_price|percent_off",
      "discount_value": "string"
    }
  ]
}
days_of_week: Monday=0, Sunday=6.
"""


def _fetch_httpx(url: str, timeout: float = 15.0) -> str:
    """Plain HTTP fallback when Firecrawl isn't configured."""
    headers = {"User-Agent": "NashGuideSocialBot/0.1 (+https://nashguide.online)"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as h:
        r = h.get(url)
        r.raise_for_status()
        return r.text


_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", re.S | re.I)
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str, max_chars: int = 18000) -> str:
    no_script = _TAG_RE.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", no_script)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_chars]


def _parse_json_block(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)


def fetch_page(url: str) -> tuple[str, str]:
    """Return (body_text, fetcher_name).

    Prefers Firecrawl markdown (cleaner, JS-rendered, better for LLMs); falls
    back to a plain httpx GET + tag-strip otherwise.
    """
    if firecrawl_client.is_configured():
        page = firecrawl_client.scrape(url)
        if page and (page.get("markdown") or page.get("html")):
            body = page.get("markdown") or _strip_html(page.get("html") or "")
            return body[:20000], "firecrawl"
        log.warning("Firecrawl returned no body for %s; falling back to httpx", url)
    raw = _fetch_httpx(url)
    return _strip_html(raw), "httpx"


def extract_from_text(
    url: str,
    body: str,
    *,
    hint: str | None = None,
) -> dict[str, Any]:
    """Run the LLM extraction over already-fetched body text."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    user_msg = f"Source URL: {url}\n\n"
    if hint:
        user_msg += f"Hint: {hint}\n\n"
    user_msg += f"Page text:\n{body[:18000]}\n\nReturn JSON in this schema only:\n{SCRAPE_SCHEMA}"
    msg = client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=2000,
        system=SCRAPE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    out = _parse_json_block(msg.content[0].text)
    out.setdefault("venue", {})["website"] = out.get("venue", {}).get("website") or url
    return out


def scrape_venue(url: str) -> dict[str, Any]:
    """Fetch `url`, ask Claude to extract structured data, return the dict.

    Raises httpx.HTTPError on fetch failure, json.JSONDecodeError on bad
    model output, anthropic exceptions on API failure. Callers should catch
    and surface a friendly message.
    """
    body, fetcher = fetch_page(url)
    out = extract_from_text(url, body)
    log.info(
        "scrape_venue ok url=%s fetcher=%s specials=%d",
        url, fetcher, len(out.get("specials") or []),
    )
    return out
