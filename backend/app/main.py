"""Loan Tape Analytics API."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import analytics  # noqa: F401  (imports register all charts)
from .api import analytics as analytics_api
from .api import portfolios, structuring, uploads
from .config import FRONTEND_ORIGINS, ensure_dirs
from .db import init_db

app = FastAPI(title="STRATA — Structured Risk & Tranche Analytics", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    init_db()


app.include_router(portfolios.router)
app.include_router(analytics_api.router)
app.include_router(uploads.router)
app.include_router(structuring.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Production mode: if the frontend has been built (frontend/dist exists), serve it
# directly so the whole app runs from this one server — no Node needed at runtime.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_DIST):
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
