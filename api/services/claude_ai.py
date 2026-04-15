"""Anthropic Claude itinerary generation."""
import json
from anthropic import Anthropic
from api.config import settings

_client: Anthropic | None = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """You are NashGuide AI — a lifelong Nashville local writing a personalized trip plan for a visitor.
Your voice is casual, opinionated, and specific. You sound like a friend who's lived in East Nashville for 15 years,
drinks at the same honky-tonks every week, and knows exactly what to order where.

Rules:
- Use ONLY venues from the provided venue list. Never invent venues.
- Be specific: name dishes to order, songs to request, where to sit, when to arrive.
- Include exact timing (e.g., "7:30pm — walk to...").
- Drop real insider tips, not generic tourist advice.
- Return ONLY valid JSON matching the schema. No prose outside the JSON."""


SCHEMA = """{
  "trip_title": "string — catchy title like 'Your Broadway-To-Bluebird Weekend'",
  "summary": "2-3 sentence intro in the local-friend voice",
  "days": [
    {
      "day_number": 1,
      "date_label": "Friday",
      "theme": "one-line theme for the day",
      "blocks": [
        {
          "time": "10:00am",
          "venue_id": 42,
          "venue_name": "Biscuit Love",
          "activity": "Brunch",
          "why": "specific reason + what to order",
          "duration_min": 75,
          "insider_tip": "string"
        }
      ]
    }
  ],
  "packing_list": ["string"],
  "spotify_vibe": "one-line playlist suggestion",
  "closing_note": "friendly send-off"
}"""


def build_prompt(quiz: dict, venues: list[dict]) -> str:
    return f"""Plan a trip with these inputs:

QUIZ ANSWERS:
- Visit dates: {quiz.get('visit_dates')}
- Days: {quiz.get('num_days')}
- Group: {quiz.get('group_type')}
- Vibe: {quiz.get('vibe')}
- Budget: {quiz.get('budget')}
- Must-dos: {quiz.get('must_dos') or 'none specified'}

AVAILABLE VENUES (use only these — reference by id):
{json.dumps(venues, indent=2)}

Return JSON in exactly this schema:
{SCHEMA}
"""


def generate_itinerary(quiz: dict, venues: list[dict]) -> dict:
    msg = client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(quiz, venues)}],
    )
    text = msg.content[0].text.strip()
    # tolerate fenced blocks
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)


def generate_blog_post(topic: str) -> dict:
    prompt = f"""Write an SEO-optimized blog post for NashGuide AI on the topic: "{topic}".
Voice: Nashville local, casual, opinionated, specific.
Length: 900-1200 words.
Return JSON: {{"title": "...", "slug": "...", "meta_description": "...", "keywords": ["..."], "content_md": "..."}}"""
    msg = client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)


def generate_tweets(n: int = 3) -> list[str]:
    prompt = f"""Write {n} distinct tweets promoting NashGuide AI — an AI-personalized Nashville trip planner.
Voice: Nashville local, punchy, not salesy. Each under 240 chars. Include 1-2 relevant hashtags.
Return a JSON array of strings only."""
    msg = client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    return json.loads(text)
