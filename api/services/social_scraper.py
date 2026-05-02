"""Stub for AI-driven happy-hour scraping.

The scaffold lives so admins can paste a venue URL and have an LLM extract
specials. Results are *never* written directly to live tables — they go into
`user_submissions` with `source='scraped'` so a human approves them.

`scrape_venue` is the public entry point. It does the HTTP fetch, hands the
text body to the existing Anthropic client, and returns a dict shaped like
`{venue: {...}, specials: [...]}`. Errors bubble up; callers wrap.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from api.config import settings
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


def _fetch(url: str, timeout: float = 15.0) -> str:
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


def scrape_venue(url: str) -> dict[str, Any]:
    """Fetch `url`, ask Claude to extract structured data, return the dict.

    Raises httpx.HTTPError on fetch failure, json.JSONDecodeError on bad
    model output, anthropic exceptions on API failure. Callers should catch
    and surface a friendly message.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    raw = _fetch(url)
    body = _strip_html(raw)

    msg = client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=2000,
        system=SCRAPE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Source URL: {url}\n\n"
                    f"Page text:\n{body}\n\n"
                    f"Return JSON in this schema only:\n{SCRAPE_SCHEMA}"
                ),
            }
        ],
    )
    out = _parse_json_block(msg.content[0].text)
    out.setdefault("venue", {})["website"] = out.get("venue", {}).get("website") or url
    log.info("scrape_venue ok url=%s specials=%d", url, len(out.get("specials") or []))
    return out
