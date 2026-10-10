"""Dashboard metrics and demo/sensor control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_state
from app.core.runtime import AppState
from app.db.database import get_db
from app.db.models import SensorCalibration
from app.schemas import (
    CalibrateRequest,
    CalibrateResponse,
    DemoControlResponse,
    MetricsResponse,
    SensorReadingResponse,
    SensorStatus,
    TareResponse,
)
from app.services.metrics import compute_metrics
from src.sensors.weight_sensor import SensorError

router = APIRouter(tags=["control"])


# --------------------------------------------------------------------------- metrics
@router.get("/metrics", response_model=MetricsResponse)
def metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    return compute_metrics(db)


# --------------------------------------------------------------------------- demo
@router.post("/demo/start", response_model=DemoControlResponse)
def demo_start(state: AppState = Depends(get_state)) -> DemoControlResponse:
    state.demo.start()
    state.broadcast(
        {"type": "demo", "message": "Demo started — SIMULATED DATA.", "demo": state.demo.status()}
    )
    return DemoControlResponse(ok=True, message="Demo started (simulated data).", demo=state.demo.status())


@router.post("/demo/stop", response_model=DemoControlResponse)
def demo_stop(state: AppState = Depends(get_state)) -> DemoControlResponse:
    state.demo.stop()
    state.broadcast({"type": "demo", "message": "Demo stopped.", "demo": state.demo.status()})
    return DemoControlResponse(ok=True, message="Demo stopped.", demo=state.demo.status())


@router.post("/demo/pause", response_model=DemoControlResponse)
def demo_pause(state: AppState = Depends(get_state)) -> DemoControlResponse:
    state.demo.pause()
    state.broadcast({"type": "demo", "message": "Demo paused.", "demo": state.demo.status()})
    return DemoControlResponse(ok=True, message="Demo paused.", demo=state.demo.status())


@router.post("/demo/resume", response_model=DemoControlResponse)
def demo_resume(state: AppState = Depends(get_state)) -> DemoControlResponse:
    state.demo.resume()
    state.broadcast({"type": "demo", "message": "Demo resumed.", "demo": state.demo.status()})
    return DemoControlResponse(ok=True, message="Demo resumed.", demo=state.demo.status())


@router.post("/demo/reset", response_model=DemoControlResponse)
def demo_reset(state: AppState = Depends(get_state)) -> DemoControlResponse:
    state.demo.reset()
    return DemoControlResponse(ok=True, message="Demo sequence reset.", demo=state.demo.status())


# --------------------------------------------------------------------------- sensor
@router.get("/sensor/status", response_model=SensorStatus)
def sensor_status(state: AppState = Depends(get_state)) -> SensorStatus:
    return SensorStatus(**state.sensor.status())


@router.post("/sensor/tare", response_model=TareResponse)
def sensor_tare(state: AppState = Depends(get_state)) -> TareResponse:
    try:
        reading = state.sensor.tare()
    except SensorError as exc:
        raise HTTPException(status_code=503, detail=f"Tare failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Tare failed: {exc}") from exc
    return TareResponse(
        ok=True,
        message=reading.message or "Tare complete.",
        sensor=SensorStatus(**state.sensor.status()),
    )


@router.post("/sensor/calibrate", response_model=CalibrateResponse)
def sensor_calibrate(
    payload: CalibrateRequest,
    state: AppState = Depends(get_state),
    db: Session = Depends(get_db),
) -> CalibrateResponse:
    try:
        factor = state.sensor.calibrate(payload.reference_weight_g, samples=payload.samples)
    except SensorError as exc:
        raise HTTPException(status_code=503, detail=f"Calibration failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = dict(getattr(state.sensor, "calibration_meta", {}) or {})
    db.add(
        SensorCalibration(
            port=str(getattr(state.sensor, "port", "") or ""),
            scale_name="scale-1",
            calibration_factor=factor,
            reference_weight_g=payload.reference_weight_g,
            raw_reading_at_calibration=meta.get("raw_reading_at_calibration"),
            notes="Simulated calibration (mock sensor)."
            if state.sensor.simulated
            else "Hardware calibration via API.",
        )
    )
    db.commit()
    return CalibrateResponse(
        ok=True,
        message=f"Calibrated (factor={factor:.6f}).",
        calibration_factor=factor,
        sensor=SensorStatus(**state.sensor.status()),
    )


@router.get("/sensor/reading", response_model=SensorReadingResponse)
def sensor_reading(state: AppState = Depends(get_state)) -> SensorReadingResponse:
    if state.sensor.backend == "disabled" or not state.sensor.connected:
        return SensorReadingResponse(
            weight_g=None, stable=False, source="none", message="Sensor not connected."
        )
    try:
        reading = state.sensor.read()
    except SensorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SensorReadingResponse(
        weight_g=reading.grams,
        stable=reading.stable,
        source=reading.source,  # type: ignore[arg-type]
        raw=reading.raw,
        message=reading.message,
    )
