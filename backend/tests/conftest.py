"""Backend test fixtures: isolated database + FastAPI TestClient per test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.runtime import AppState
from app.db import models
from app.db.database import SessionLocal, engine
from app.services.catalogue import seed_demo_products


def reset_database() -> None:
    """Drop and recreate all tables, then seed the demo catalogue."""
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_demo_products(db)
    finally:
        db.close()


@pytest.fixture()
def app_state(client: TestClient) -> AppState:
    return client.app.state.station


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        reset_database()
        state: AppState = test_client.app.state.station
        # The scan service caches catalogue rows — invalidate after reset.
        state.scans._products = []
        state.scans._products_loaded_at = 0.0
        state.scans._last_persist_at = 0.0
        state.scans._last_status = ""
        state.demo.stop()
        state.demo.reset()
        yield test_client
        state.demo.stop()
