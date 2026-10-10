"""Model lifecycle: baseline (pretrained YOLO) and custom (user-trained) weights.

Both modes are explicit:

* ``baseline`` — a small pretrained Ultralytics YOLO model. It recognises
  everyday *object* classes (person, cup, bottle, apple, ...). It is **not**
  a SKU-level product classifier and results are labelled as such.
* ``custom``  — user-trained product weights loaded from a configurable path.
  Class names come from the model file itself (``model.names``).

Import of ``ultralytics``/``torch`` is deliberately lazy so the server can run
(demo mode) even when heavy vision dependencies or weights are unavailable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from app.core.config import Settings

_ULTRALYTICS_HINT = (
    "ultralytics is not installed. Install backend requirements "
    "(pip install -r requirements.txt) to enable live detection, "
    "or use demo mode."
)


@dataclass
class ModelInfo:
    """Immutable snapshot of the loaded model's state."""

    mode: str = "baseline"
    available: bool = False
    model_name: str = ""
    weights_path: str = ""
    weights_present: bool = False
    classes: list[str] = field(default_factory=list)
    is_generic_detector: bool = True
    message: str = ""

    @property
    def class_count(self) -> int:
        return len(self.classes)

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "available": self.available,
            "model_name": self.model_name,
            "weights_path": self.weights_path,
            "weights_present": self.weights_present,
            "classes": self.classes,
            "class_count": self.class_count,
            "message": self.message,
            "is_generic_detector": self.is_generic_detector,
        }


class ModelLoadError(RuntimeError):
    """Raised when weights for the requested mode cannot be loaded."""


class ModelManager:
    """Thread-safe lazy loader for YOLO models."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._model: Any = None
        self._info = ModelInfo(mode=settings.inference_mode)

    # ------------------------------------------------------------------ state
    @property
    def info(self) -> ModelInfo:
        return self._info

    @property
    def model(self) -> Any:
        return self._model

    def resolve_weights(self, mode: str) -> Path | None:
        """Return an existing weights file for *mode*, or ``None``."""
        s = self._settings
        if mode == "custom":
            return s.custom_weights_path
        candidate = s.models_dir / s.baseline_weights
        if candidate.exists():
            return candidate
        return None

    # ------------------------------------------------------------------ loading
    def load(self, mode: str | None = None, force: bool = False) -> ModelInfo:
        """Load (or reload) the model for *mode*. Returns the resulting info.

        Never raises for missing files — the returned :class:`ModelInfo`
        carries an explanatory message instead, so the API can stay up.
        """
        mode = (mode or self._settings.inference_mode).lower()
        if mode not in {"baseline", "custom"}:
            mode = "baseline"

        with self._lock:
            if not force and self._model is not None and self._info.mode == mode:
                return self._info
            try:
                self._info = self._load_locked(mode)
            except Exception as exc:  # noqa: BLE001 - surface as status, not crash
                self._model = None
                self._info = ModelInfo(
                    mode=mode,
                    available=False,
                    message=f"Failed to load model: {exc}",
                )
            return self._info

    def _load_locked(self, mode: str) -> ModelInfo:
        s = self._settings
        self._model = None  # reset; assigned again on successful load
        try:
            from ultralytics import YOLO  # type: ignore[import-not-found]
        except Exception as exc:  # ImportError or a broken torch install
            return ModelInfo(mode=mode, available=False, message=_ULTRALYTICS_HINT + f" ({exc})")

        if mode == "custom":
            weights = s.custom_weights_path
            if weights is None:
                configured = s.custom_weights or ""
                if not configured:
                    message = (
                        "Custom weights path is not configured. Set the CUSTOM_WEIGHTS "
                        "environment variable to a trained .pt file (train one with "
                        "scripts/train_model.py). Falling back to baseline or demo mode "
                        "is possible."
                    )
                else:
                    message = (
                        f"Custom product weights not found at {configured!r}. Train a "
                        "model with scripts/train_model.py and point CUSTOM_WEIGHTS at "
                        "the resulting .pt file. Falling back to baseline/demo is possible."
                    )
                return ModelInfo(
                    mode="custom",
                    available=False,
                    weights_path=configured or "(not configured — set CUSTOM_WEIGHTS)",
                    weights_present=False,
                    is_generic_detector=False,
                    message=message,
                )
            model = YOLO(str(weights))
            self._model = model
            self._warmup(model)
            classes = [str(v) for v in (model.names or {}).values()]
            return ModelInfo(
                mode="custom",
                available=True,
                model_name=weights.name,
                weights_path=str(weights),
                weights_present=True,
                classes=classes,
                is_generic_detector=False,
                message=f"Custom product model loaded ({len(classes)} classes).",
            )

        # baseline ------------------------------------------------------------
        weights = s.baseline_weights_path
        source = str(weights) if weights else s.baseline_weights
        model = YOLO(source)  # may auto-download to ultralytics assets dir
        self._model = model
        self._warmup(model)
        classes = [str(v) for v in (model.names or {}).values()]
        resolved = source
        if weights is None:
            # YOLO may have resolved a bare filename inside the assets folder.
            try:
                best = getattr(model, "ckpt_path", None)
                if best:
                    resolved = str(best)
            except Exception:  # pragma: no cover
                pass
        return ModelInfo(
            mode="baseline",
            available=True,
            model_name=Path(source).name,
            weights_path=resolved,
            weights_present=True,
            classes=classes,
            is_generic_detector=True,
            message=(
                "Baseline COCO-pretrained detector. Results are generic object "
                "classes, not exact product/SKU recognition."
            ),
        )

    @staticmethod
    def _warmup(model: Any) -> None:
        """Run one dummy inference so kernels are compiled before real frames."""
        try:
            import numpy as np

            dummy = np.zeros((320, 320, 3), dtype=np.uint8)
            model.predict(source=dummy, imgsz=320, verbose=False, device="cpu")
        except Exception:  # pragma: no cover - warmup must never break loading
            pass

    def preload_async(self) -> threading.Thread:
        """Load the configured model on a background thread (keeps startup fast)."""
        t = threading.Thread(target=self.load, name="model-loader", daemon=True)
        t.start()
        return t


def wait_until_loaded(manager: ModelManager, timeout: float = 30.0) -> ModelInfo:
    """Block until the background loader finished (used by tests)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = manager.info
        if info.message or info.available:
            return info
        time.sleep(0.05)
    return manager.info
