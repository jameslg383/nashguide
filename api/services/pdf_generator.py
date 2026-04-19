"""PDF itinerary generation via WeasyPrint."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_PDF_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "trips"
STATIC_PDF_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_itinerary_pdf(itinerary: dict, slug: str) -> str:
    tpl = env.get_template("itinerary_pdf.html")
    html = tpl.render(trip=itinerary)
    out_path = STATIC_PDF_DIR / f"{slug}.pdf"
    HTML(string=html).write_pdf(str(out_path))
    return f"/static/trips/{slug}.pdf"


def render_itinerary_html(itinerary: dict) -> str:
    tpl = env.get_template("itinerary_web.html")
    return tpl.render(trip=itinerary)
