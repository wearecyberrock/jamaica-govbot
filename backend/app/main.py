"""FastAPI application entry point for Jahtaria Visa Intelligence & Document Automation."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import APP_ENV, APP_NAME, LOGO_PATH
from app.database import SessionLocal, init_db
from app.routers import (
    agent_router,
    auth_router,
    ceo_settings_router,
    clients_router,
    database_router,
    documents_router,
    interviews_router,
    obsidian_router,
)
from app.seed import seed_all


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=f"{APP_NAME} — Visa Intelligence & Document Automation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(clients_router.router)
app.include_router(interviews_router.router)
app.include_router(documents_router.router)
app.include_router(database_router.router)
app.include_router(obsidian_router.router)
app.include_router(agent_router.router)
app.include_router(ceo_settings_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_NAME, "mode": APP_ENV}


@app.get("/api/branding/logo")
def serve_branding_logo() -> FileResponse:
    return FileResponse(path=str(LOGO_PATH), media_type="image/png")
