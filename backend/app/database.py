"""SQLAlchemy 2.0 database engine (SQLite desktop default, PostgreSQL VPS-ready)."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}

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
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
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
    migrations = [
        ("risk_flags", "options_json", "TEXT DEFAULT '[]'"),
        ("users", "username", "VARCHAR(128)"),
        ("users", "all_tiers", "BOOLEAN DEFAULT 0"),
        ("users", "recovery_pin_hash", "VARCHAR(512) DEFAULT ''"),
        ("users", "reset_code_hash", "VARCHAR(512) DEFAULT ''"),
        ("users", "reset_code_expires_at", "DATETIME"),
        ("clients", "email_muted", "BOOLEAN DEFAULT 0"),
    ]
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        for tbl, col, col_def in migrations:
            if tbl in tables:
                cols = {c["name"] for c in insp.get_columns(tbl)}
                if col not in cols:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}"))
        # Backfill username for legacy users who only had email
        if "users" in tables:
            with engine.begin() as conn:
                rows = conn.execute(text("SELECT id, email, username FROM users")).fetchall()
                used = {str(r[2]).lower() for r in rows if r[2]}
                for uid, email, uname in rows:
                    if not uname:
                        base = (str(email or f"user{uid}").split("@")[0]).lower().strip() or f"user{uid}"
                        cand = base
                        n = 1
                        while cand in used:
                            n += 1
                            cand = f"{base}{n}"
                        used.add(cand)
                        conn.execute(text("UPDATE users SET username = :u WHERE id = :id"), {"u": cand, "id": uid})
    except Exception:
        pass
