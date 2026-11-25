"""SQLAlchemy 2.0 database engine (SQLite desktop default, PostgreSQL VPS-ready)."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Safe additive column migrations for existing desktop SQLite databases
    try:
        insp = inspect(engine)
        if "risk_flags" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("risk_flags")}
            if "options_json" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE risk_flags ADD COLUMN options_json TEXT DEFAULT '[]'"))
    except Exception:
        pass
