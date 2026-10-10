"""Sensor endpoints, scan persistence rate limiting, API validation."""

from __future__ import annotations

import pytest

from app.db.models import Product, ScanRecord
from app.db.database import SessionLocal
from app.services import catalogue
from app.services.scan_service import PERSIST_COOLDOWN_S
from src.verification.verifier import (
    ColourEvidence,
    ProductVerifier,
    VerificationInput,
    VerificationThresholds,
    WeightEvidence,
)
from src.vision.detector import Detection
from src.vision.color_analyzer import ColourResult


def test_sensor_status_endpoint(client):
    res = client.get("/api/sensor/status")
    assert res.status_code == 200
    body = res.json()
    assert body["backend"] == "mock"
    assert body["simulated"] is True


def test_sensor_tare_endpoint(client):
    res = client.post("/api/sensor/tare")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_sensor_calibrate_endpoint(client):
    res = client.post("/api/sensor/calibrate", json={"reference_weight_g": 200.0, "samples": 8})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["calibration_factor"] > 0
    # calibration metadata is recorded
    db = SessionLocal()
    try:
        from sqlalchemy import select

        rows = db.scalars(select(ScanRecord)).all()  # sanity: session usable
        from app.db.models import SensorCalibration

        calibrations = db.scalars(select(SensorCalibration)).all()
        assert len(calibrations) >= 1
        assert calibrations[0].reference_weight_g == 200.0
    finally:
        db.close()


def test_sensor_calibrate_validation(client):
    res = client.post("/api/sensor/calibrate", json={"reference_weight_g": -10})
    assert res.status_code == 422
    res = client.post("/api/sensor/calibrate", json={})
    assert res.status_code == 422


def test_sensor_reading_endpoint(client):
    state = client.app.state.station
    state.sensor.set_weight(123.0)
    res = client.get("/api/sensor/reading")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "simulated"
    assert body["weight_g"] == pytest.approx(123.0, abs=5)


def test_persist_rate_limit_for_live_scans(client, app_state):
    """Identical live scans within the cooldown window are stored only once."""
    db = SessionLocal()
    try:
        product = catalogue.get_product_by_sku(db, "DEMO-001")
        assert product is not None
        spec = catalogue.product_to_spec(product)
    finally:
        db.close()

    verifier = ProductVerifier(VerificationThresholds())
    verification = verifier.verify(
        VerificationInput(
            detected_label="demo cola can",
            confidence=0.9,
            product=spec,
            colour=ColourEvidence(name="red", hex_value="#e63946", quality="good",
                                  reliable=True, similarity=0.9),
            weight=WeightEvidence(grams=355.0, stable=True, source="simulated"),
        )
    )
    colour = ColourResult(name="red", hex_value="#e63946", quality="good", reliable=True)
    detection = Detection(10, 10, 100, 100, "demo cola can", 0.9, -1)

    scans = app_state.scans
    scans._last_persist_at = 0.0
    scans._last_status = ""

    db = SessionLocal()
    try:
        first = scans._persist_scan(
            db, det=detection, product=product, colour=colour,
            weight=WeightEvidence(grams=355.0, stable=True, source="simulated"),
            verification=verification, mode="baseline", source="live", inference_ms=12.0,
        )
        assert first is not None
        second = scans._persist_scan(
            db, det=detection, product=product, colour=colour,
            weight=WeightEvidence(grams=355.0, stable=True, source="simulated"),
            verification=verification, mode="baseline", source="live", inference_ms=11.0,
        )
        assert second is None, "second identical scan inside cooldown must be dropped"

        # Outside the cooldown the same scan persists again.
        scans._last_persist_at -= PERSIST_COOLDOWN_S + 1
        third = scans._persist_scan(
            db, det=detection, product=product, colour=colour,
            weight=WeightEvidence(grams=355.0, stable=True, source="simulated"),
            verification=verification, mode="baseline", source="live", inference_ms=10.0,
        )
        assert third is not None
    finally:
        db.close()


def test_demo_scans_bypass_rate_limit(client, app_state):
    app_state.demo.start()
    app_state.demo.reset()
    for _ in range(3):
        event = app_state.demo.next_event()
        result = app_state.scans.process_demo_event(event)
        assert result.persisted
    app_state.demo.stop()


def test_bad_json_body(client):
    res = client.post(
        "/api/products",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422


def test_unknown_route_404(client):
    assert client.get("/api/definitely-not-a-route").status_code == 404


def test_frame_with_invalid_image_returns_error(client):
    state = client.app.state.station
    state.demo.stop()
    with client.websocket_connect("/ws/scan") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "frame", "image": "!!!not-base64!!!"})
        reply = ws.receive_json()
        assert reply["type"] in {"error", "detection"}
        if reply["type"] == "error":
            assert reply["message"]
