"""Application runtime state: one place that owns long-lived objects."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from app.core.config import Settings
from app.services.demo_service import DemoService
from app.services.scan_service import ScanService
from src.sensors.weight_sensor import WeightSensor, create_sensor
from src.verification.verifier import ProductVerifier, VerificationThresholds
from src.vision.detector import ProductDetector
from src.vision.model_manager import ModelManager

logger = logging.getLogger("smart_station")

BroadcastFn = Callable[[dict], None]


class AppState:
    """Holds the detector, sensor, verifier, demo sequencer and services."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started_at = time.time()
        self.model_manager = ModelManager(settings)
        self.detector = ProductDetector(settings, self.model_manager)
        self.sensor: WeightSensor = create_sensor(settings)
        self.verifier = ProductVerifier(
            VerificationThresholds(
                min_confidence=settings.verify_min_confidence,
                weight_tolerance_pct=settings.verify_weight_tolerance_pct,
                colour_min_similarity=settings.verify_colour_min_similarity,
                require_stable_weight=settings.verify_stable_weight_required,
            )
        )
        self.demo = DemoService(tick_ms=settings.demo_tick_ms)
        self.scans: ScanService | None = None  # set after DB init
        self.broadcast: BroadcastFn = lambda msg: None
        self._ticker: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Effective mode: "demo" while the demo sequencer runs, otherwise the
        # configured inference mode.
        self.active_mode = settings.inference_mode

    # ------------------------------------------------------------------ lifecycle
    def attach_scans(self, scans: ScanService) -> None:
        self.scans = scans

    def start_background(self) -> None:
        """Start model preloading and the demo ticker (idempotent)."""
        if self.settings.preload_model and self.settings.inference_mode in (
            "baseline",
            "custom",
        ):
            self.model_manager.preload_async()
        if self._ticker is None or not self._ticker.is_alive():
            self._stop_event.clear()
            self._ticker = threading.Thread(
                target=self._tick_loop, name="demo-ticker", daemon=True
            )
            self._ticker.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._ticker is not None:
            self._ticker.join(timeout=2.0)
        try:
            self.sensor.disconnect()
        except Exception:  # pragma: no cover
            logger.exception("Sensor disconnect failed")

    # ------------------------------------------------------------------ demo loop
    def _tick_loop(self) -> None:
        while not self._stop_event.is_set():
            tick = max(150, self.settings.demo_tick_ms)
            self._stop_event.wait(tick / 1000.0)
            if not self.demo.active or self.demo.paused:
                continue
            if self.scans is None:
                continue
            try:
                event = self.demo.next_event()
                if event is None:
                    continue
                result = self.scans.process_demo_event(event)
                message = {
                    "type": "detection",
                    "seq": event.seq,
                    "ts": time.time(),
                    "inference_ms": 0.0,
                    "fps": round(1000.0 / tick, 1),
                    "mode": "demo",
                    "annotated": result.annotated_b64,
                    "boxes": [b.model_dump() for b in result.boxes],
                    "primary": result.primary.model_dump() if result.primary else None,
                    "scan_id": result.scan.scan_id if result.scan else None,
                    "message": event.note,
                    "warnings": result.warnings,
                    "demo": self.demo.status(),
                }
                self.broadcast(message)
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("Demo tick failed")

    # ------------------------------------------------------------------ status
    @property
    def mode(self) -> str:
        return "demo" if self.demo.active else self.active_mode

    def set_mode(self, mode: str) -> None:
        self.active_mode = mode

    def inference_status(self) -> dict[str, Any]:
        info = self.model_manager.info
        if self.demo.active:
            payload = info.to_status_dict()
            payload.update(
                {
                    "mode": "demo",
                    "message": "Demo mode active — synthetic detections, model not used.",
                }
            )
            return payload
        if not info.message and not info.available:
            if self.settings.preload_model:
                # Loader has not finished yet (or failed silently) — load now.
                info = self.model_manager.load(self.active_mode)
            else:
                return {
                    **info.to_status_dict(),
                    "message": "Model not loaded (auto-load disabled in this environment).",
                }
        return info.to_status_dict()

    def dataset_status(self) -> dict[str, Any]:
        config_path = self.settings.dataset_config_path
        datasets_dir = self.settings.data_dir / "datasets"
        prepared: list[str] = []
        if datasets_dir.exists():
            prepared = sorted(
                p.name for p in datasets_dir.iterdir() if p.is_dir() and any(p.iterdir())
            )
        return {
            "config_path": str(config_path),
            "config_exists": config_path.exists(),
            "datasets_dir": str(datasets_dir),
            "prepared_datasets": prepared,
            "message": (
                "Dataset tools ready — see docs/DATASETS.md. No dataset is required "
                "to run the application."
                if not prepared
                else f"{len(prepared)} prepared dataset(s) found."
            ),
        }
