from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.models.database import get_db
from api.models.content import Waitlist

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])


class WaitlistPayload(BaseModel):
    email: EmailStr
    source: str | None = None


@router.post("")
def join_waitlist(payload: WaitlistPayload, db: Session = Depends(get_db)):
    try:
        w = Waitlist(email=payload.email, source=payload.source)
        db.add(w)
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ok": True}
