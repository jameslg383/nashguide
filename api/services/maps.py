"""Google Static Maps helpers + Google Maps deep links."""
from urllib.parse import quote_plus
from api.config import settings


def static_map_url(markers: list[tuple[float, float]], size: str = "640x360", zoom: int = 12) -> str:
    if not markers or not settings.GOOGLE_MAPS_API_KEY:
        return ""
    marker_params = "&".join(
        f"markers=color:red%7Clabel:{i+1}%7C{lat},{lng}"
        for i, (lat, lng) in enumerate(markers)
    )
    return (
        f"https://maps.googleapis.com/maps/api/staticmap?size={size}&zoom={zoom}"
        f"&{marker_params}&key={settings.GOOGLE_MAPS_API_KEY}"
    )


def google_maps_link(address: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"
