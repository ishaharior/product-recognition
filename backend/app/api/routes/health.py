"""Health and status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_state
from app.core.runtime import AppState
from app.schemas import DatasetStatus, DemoStatus, HealthResponse, ModelStatus, SensorStatus, StatusResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(time=datetime.now(timezone.utc))


@router.get("/status", response_model=StatusResponse)
def status(state: AppState = Depends(get_state)) -> StatusResponse:
    inference = ModelStatus(**state.inference_status())
    sensor = SensorStatus(**state.sensor.status())
    demo = DemoStatus(**state.demo.status())
    dataset = DatasetStatus(**state.dataset_status())
    return StatusResponse(
        inference=inference,
        sensor=sensor,
        demo=demo,
        dataset=dataset,
        camera_expected=True,
        fps_limit=state.settings.max_incoming_fps,
        frame_max_size=[
            state.settings.max_frame_width,
            state.settings.max_frame_height,
        ],
    )
