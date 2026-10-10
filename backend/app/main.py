"""FastAPI application entry point.

Launch (from the repository root):

    python -m uvicorn app.main:app --app-dir backend --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import control, health, products, scans, ws
from app.api.ws_manager import ConnectionManager
from app.core.config import REPO_ROOT, settings
from app.core.runtime import AppState
from app.db.database import SessionLocal, init_db
from app.services.catalogue import seed_demo_products, seed_from_csv
from app.services.scan_service import ScanService

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("smart_station")

DESCRIPTION = """
Smart Product Station — live product recognition, colour analysis,
physical weight measurement and explainable verification.

Camera frames are sent from the browser over WebSocket `/ws/scan`.
Demo mode works without camera, sensor, custom weights or datasets.
"""

ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database, seed the catalogue and start background work."""
    init_db()
    db = SessionLocal()
    try:
        created_demo = seed_demo_products(db)
        created_csv, csv_errors = seed_from_csv(db, settings.product_spec_csv)
        if created_demo or created_csv:
            logger.info(
                "Catalogue seeded (%d demo, %d csv entries)", created_demo, created_csv
            )
        for err in csv_errors:
            logger.warning("product_specs.csv: %s", err)
    finally:
        db.close()

    state = AppState(settings)
    scans = ScanService(settings, state.detector, state.sensor, state.verifier, SessionLocal)
    state.attach_scans(scans)
    state.broadcast = ws_manager.broadcast_threadsafe
    state.start_background()

    app.state.station = state
    app.state.ws_manager = ws_manager
    logger.info(
        "Smart Product Station started (mode=%s, sensor=%s)",
        settings.inference_mode,
        settings.sensor_backend,
    )
    try:
        yield
    finally:
        state.shutdown()
        logger.info("Smart Product Station shut down")


app = FastAPI(
    title="Smart Product Station",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)
app.state.ws_manager = ws_manager

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(scans.router, prefix="/api")
app.include_router(control.router, prefix="/api")
app.include_router(ws.router)  # WebSocket at /ws/scan


@app.get("/api", include_in_schema=False)
def api_root() -> dict:
    return {"docs": "/docs", "health": "/api/health", "status": "/api/status"}


def _mount_frontend_build() -> None:
    """Serve the built frontend (if present) for single-origin deployments."""
    dist = REPO_ROOT / "frontend" / "dist"
    if not dist.is_dir():
        return
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    logger.info("Serving frontend build from %s", dist)


_mount_frontend_build()
