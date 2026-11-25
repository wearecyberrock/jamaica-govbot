"""FastAPI application entry point for Jahtaria Visa Intelligence & Document Automation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import APP_ENV, APP_NAME, LOGO_PATH, STATIC_FRONTEND_DIR
from app.database import SessionLocal, init_db
from app.routers import (
    agent_router,
    auth_router,
    ceo_settings_router,
    clients_router,
    database_router,
    documents_router,
    gmail_router,
    interviews_router,
    oauth_voice_router,
    obsidian_router,
)
from app.seed import seed_all
from app.services.gmail_service import background_cron_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()
    cron_task = asyncio.create_task(background_cron_worker(SessionLocal))
    try:
        yield
    finally:
        cron_task.cancel()
        try:
            await cron_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=f"{APP_NAME} Alpha — Visa Intelligence & Document Automation API",
    version="2.3.0-alpha",
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
app.include_router(oauth_voice_router.router)
app.include_router(gmail_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_NAME, "mode": APP_ENV}


@app.get("/api/branding/logo")
def serve_branding_logo() -> FileResponse:
    return FileResponse(path=str(LOGO_PATH), media_type="image/png")


# Serve static exported Next.js frontend when bundled in the standalone Desktop Setup.exe
if STATIC_FRONTEND_DIR and STATIC_FRONTEND_DIR.exists() and (STATIC_FRONTEND_DIR / "index.html").exists():

    @app.get("/{full_path:path}")
    def serve_static_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "mcp" or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found")
        base = STATIC_FRONTEND_DIR.resolve()
        clean = full_path.strip("/")
        candidates: list[Path] = []
        if not clean:
            candidates.append(base / "index.html")
        else:
            candidates.extend(
                [
                    base / clean,
                    base / clean / "index.html",
                    base / f"{clean}.html",
                    base / "index.html",
                ]
            )
        for cand in candidates:
            resolved = cand.resolve()
            if str(resolved).startswith(str(base)) and resolved.is_file():
                return FileResponse(str(resolved))
        raise HTTPException(status_code=404, detail="Frontend asset not found")
