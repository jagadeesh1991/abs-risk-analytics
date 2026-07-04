"""Application paths and settings."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TAPES_DIR = DATA_DIR / "tapes"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.sqlite"

FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, TAPES_DIR, UPLOADS_DIR):
        d.mkdir(parents=True, exist_ok=True)
