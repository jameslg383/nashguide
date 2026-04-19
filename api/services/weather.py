"""Nashville weather forecast via Open-Meteo (no API key, free).

The trip date range comes from the fuzzy quiz answer ("This weekend" /
"Next week" / "This month" / "Pick dates"). We parse it into an actual
date window, hit Open-Meteo's 16-day forecast, and return per-day cards
that the PDF + web templates can render.
"""
import logging
from datetime import date, datetime, timedelta

import httpx

log = logging.getLogger("weather")

NASHVILLE_LAT = 36.1627
NASHVILLE_LON = -86.7816
FORECAST_WINDOW_DAYS = 16   # Open-Meteo free-tier forecast horizon


# -- WMO weather-code translation -------------------------------------------
# https://open-meteo.com/en/docs — "WMO Weather interpretation codes"
_CODE_MAP = {
    0:  ("Clear sky",       "☀️"),
    1:  ("Mostly sunny",    "🌤️"),
    2:  ("Partly cloudy",   "⛅"),
    3:  ("Overcast",        "☁️"),
    45: ("Fog",             "🌫️"),
    48: ("Icy fog",         "🌫️"),
    51: ("Light drizzle",   "🌦️"),
    53: ("Drizzle",         "🌦️"),
    55: ("Heavy drizzle",   "🌧️"),
    61: ("Light rain",      "🌦️"),
    63: ("Rain",            "🌧️"),
    65: ("Heavy rain",      "🌧️"),
    71: ("Light snow",      "🌨️"),
    73: ("Snow",            "🌨️"),
    75: ("Heavy snow",      "❄️"),
    77: ("Snow grains",     "❄️"),
    80: ("Rain showers",    "🌦️"),
    81: ("Heavy showers",   "🌧️"),
    82: ("Violent showers", "⛈️"),
    85: ("Snow showers",    "🌨️"),
    86: ("Heavy snow",      "❄️"),
    95: ("Thunderstorm",    "⛈️"),
    96: ("T-storm w/ hail", "⛈️"),
    99: ("Severe t-storm",  "⛈️"),
}


def _describe(code: int) -> tuple[str, str]:
    return _CODE_MAP.get(code, ("Unknown", "🌡️"))


def parse_visit_dates(visit_dates: str, num_days: int) -> tuple[date, date]:
    """Turn the free-text quiz answer into a concrete (start, end) date window.

    The quiz options are "This weekend", "Next week", "This month", "Pick dates"
    — there's no real date picker yet, so this is best-effort heuristic.
    """
    today = datetime.utcnow().date()
    text = (visit_dates or "").lower()
    n = max(1, min(num_days or 3, 5))

    if "weekend" in text:
        # Next Saturday (or today if it's already Sat; next Sat if it's Sun)
        offset = (5 - today.weekday()) % 7
        if offset == 0 and today.weekday() == 6:  # Sunday → next Saturday
            offset = 6
        start = today + timedelta(days=offset)
        end = start + timedelta(days=min(n, 2) - 1)
    elif "next week" in text:
        # Next Monday
        offset = (7 - today.weekday()) % 7 or 7
        start = today + timedelta(days=offset)
        end = start + timedelta(days=n - 1)
    elif "month" in text:
        # ~10 days out (roughly middle of the forecast horizon)
        start = today + timedelta(days=10)
        end = start + timedelta(days=n - 1)
    else:
        # "Pick dates" or unrecognized — default to starting in ~5 days
        start = today + timedelta(days=5)
        end = start + timedelta(days=n - 1)
    return start, end


def _format_label(d: date) -> str:
    return d.strftime("%a %b %-d") if hasattr(d, "strftime") else str(d)


def fetch_forecast(
    visit_dates: str,
    num_days: int,
    lat: float = NASHVILLE_LAT,
    lon: float = NASHVILLE_LON,
) -> dict:
    """Return a forecast payload suitable for inclusion in content_json.

    Shape:
        {
          "period": "Sat May 3 – Sun May 4",
          "days": [{"date", "label", "high_f", "low_f",
                    "description", "emoji", "precip_chance"}, ...],
        }
    OR (if outside 16-day window / fetch fails):
        {"note": "...friendly message...", "period": "..."}
    """
    start, end = parse_visit_dates(visit_dates, num_days)
    period_label = f"{_format_label(start)} – {_format_label(end)}"

    today = datetime.utcnow().date()
    if (start - today).days > FORECAST_WINDOW_DAYS:
        return {
            "period": period_label,
            "note": "Your trip is more than 2 weeks out — we'll refresh the forecast closer to your dates.",
        }
    if end < today:
        return {
            "period": period_label,
            "note": "Trip window has already passed.",
        }

    # Clamp end to the forecast horizon so we never ask Open-Meteo for dates
    # it can't deliver.
    horizon = today + timedelta(days=FORECAST_WINDOW_DAYS)
    fetch_start = max(start, today)
    fetch_end = min(end, horizon)

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "timezone": "America/Chicago",
        "start_date": fetch_start.isoformat(),
        "end_date": fetch_end.isoformat(),
    }
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=8)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        log.warning("Open-Meteo fetch failed: %s", e)
        return {"period": period_label, "note": "Forecast temporarily unavailable."}

    daily = j.get("daily") or {}
    times = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_probability_max") or []
    codes = daily.get("weathercode") or []

    out = []
    for i, iso in enumerate(times):
        try:
            d = date.fromisoformat(iso)
        except Exception:
            continue
        desc, emoji = _describe(int(codes[i]) if i < len(codes) and codes[i] is not None else -1)
        out.append({
            "date": iso,
            "label": _format_label(d),
            "high_f": int(round(highs[i])) if i < len(highs) and highs[i] is not None else None,
            "low_f": int(round(lows[i])) if i < len(lows) and lows[i] is not None else None,
            "description": desc,
            "emoji": emoji,
            "precip_chance": int(precip[i]) if i < len(precip) and precip[i] is not None else 0,
        })

    return {
        "period": period_label,
        "source": "Open-Meteo",
        "location": "Nashville, TN",
        "days": out,
    }
