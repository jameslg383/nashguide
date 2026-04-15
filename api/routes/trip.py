from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from api.models.database import get_db
from api.models.itinerary import Itinerary
from api.services.pdf_generator import render_itinerary_html

router = APIRouter(tags=["trip"])


@router.get("/api/trip/{slug}")
def get_trip_json(slug: str, db: Session = Depends(get_db)):
    itin = db.query(Itinerary).filter(Itinerary.public_slug == slug).first()
    if not itin:
        raise HTTPException(404, "Trip not found")
    return {
        "slug": itin.public_slug,
        "status": itin.status,
        "content": itin.content_json,
        "pdf_url": itin.pdf_url,
    }


@router.get("/trip/{slug}", response_class=HTMLResponse)
def get_trip_web(slug: str, db: Session = Depends(get_db)):
    itin = db.query(Itinerary).filter(Itinerary.public_slug == slug).first()
    if not itin:
        raise HTTPException(404, "Trip not found")
    if itin.status != "delivered":
        return HTMLResponse("<h1>Your NashGuide is still being prepared…</h1>", status_code=202)
    return HTMLResponse(render_itinerary_html(itin.content_json))
