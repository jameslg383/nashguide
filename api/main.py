from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.models.database import init_db
from api.routes import quiz, payment, trip, blog, admin, waitlist

app = FastAPI(title="NashGuide AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(quiz.router)
app.include_router(payment.router)
app.include_router(trip.router)
app.include_router(blog.router)
app.include_router(waitlist.router)
app.include_router(admin.router)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": "nashguide-ai"}


@app.get("/")
def root():
    return {
        "service": "NashGuide AI",
        "tagline": "Your personalized Nashville trip, planned by a local who happens to be an AI.",
        "endpoints": ["/api/quiz/start", "/api/quiz/submit", "/api/payment/create", "/api/payment/capture", "/blog", "/trip/{slug}"],
    }
