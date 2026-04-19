from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from api.config import settings
from api.models.database import init_db
from api.routes import quiz, payment, trip, blog, admin, waitlist, analytics, admin_console, promo

app = FastAPI(title="NashGuide AI", version="0.1.0")

# Session cookie for the admin console (30 days). Signed with SECRET_KEY.
# https_only is False so it works in dev; Caddy sets X-Forwarded-Proto so the
# cookie is still attached on the HTTPS domain.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="ng_admin",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=False,
)

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
app.include_router(analytics.router)
app.include_router(admin_console.router)
app.include_router(promo.router)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": "nashguide-ai"}


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(static_dir / "index.html"))