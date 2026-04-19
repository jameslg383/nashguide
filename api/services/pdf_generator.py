"""PDF itinerary generation via WeasyPrint."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_PDF_DIR = PROJECT_ROOT / "static" / "trips"
STATIC_PDF_DIR.mkdir(parents=True, exist_ok=True)
BRAND_DIR = PROJECT_ROOT / "static" / "brand"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _brand_logo_file_url() -> str | None:
    """Return a file:// URL to the logo if one exists on disk, else None.
    WeasyPrint resolves file URLs at render time — PNG preferred, SVG fallback."""
    for name in ("nashguide-logo.png", "logo.svg"):
        p = BRAND_DIR / name
        if p.exists():
            return p.as_uri()
    return None


def render_itinerary_pdf(itinerary: dict, slug: str) -> str:
    tpl = env.get_template("itinerary_pdf.html")
    html = tpl.render(trip=itinerary, logo_path=_brand_logo_file_url())
    out_path = STATIC_PDF_DIR / f"{slug}.pdf"
    # base_url lets WeasyPrint resolve any relative URLs in the template
    # (though we use absolute file:// for the logo so it's defensive here).
    HTML(string=html, base_url=str(PROJECT_ROOT)).write_pdf(str(out_path))
    return f"/static/trips/{slug}.pdf"


def render_itinerary_html(itinerary: dict) -> str:
    tpl = env.get_template("itinerary_web.html")
    return tpl.render(trip=itinerary)
