"""SQLite metadata store (portfolios, snapshots, saved mappings)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH, ensure_dirs


class Base(DeclarativeBase):
    pass


ensure_dirs()
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)


def get_session():
    """FastAPI dependency yielding a DB session."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
