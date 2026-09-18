"""
Database connection setup.

Uses SQLAlchemy with SQLite for local dev (no external DB needed).
Swap the DATABASE_URL env var to PostgreSQL for production.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Default to SQLite for easy local development — just works, no setup.
# (Empty-string env values are treated as unset — hosts sometimes inject them.)
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./leads.db"


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# For SQLite, enforce foreign key support (off by default in SQLite)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Set True to see SQL queries in logs
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and foreign keys for SQLite."""
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called once at startup."""
    Base.metadata.create_all(bind=engine)
