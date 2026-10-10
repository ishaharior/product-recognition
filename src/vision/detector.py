"""Product/object detection on decoded frames.

Thin, testable wrapper around Ultralytics YOLO. Returns plain dataclasses so
callers (API, verifier, tests) never depend on ultralytics types directly.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Keep CPU inference quiet and deterministic-ish.
os.environ.setdefault("YOLO_VERBOSE", "False")

if TYPE_CHECKING:  # pragma: no cover
    from app.core.config import Settings

from .model_manager import ModelInfo, ModelManager  # noqa: E402


@dataclass
class Detection:
    """A single detected object. Box coordinates are pixel values (x1..y2)."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    class_id: int = -1

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def cx(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2

    def clip(self, w: int, h: int) -> "Detection":
        return Detection(
            x1=max(0, min(self.x1, w)),
            y1=max(0, min(self.y1, h)),
            x2=max(0, min(self.x2, w)),
            y2=max(0, min(self.y2, h)),
            label=self.label,
            confidence=self.confidence,
            class_id=self.class_id,
        )

    def to_dict(self) -> dict:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "class_id": self.class_id,
        }


@dataclass
class DetectionResult:
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0
    mode: str = "baseline"
    model_name: str = ""
    image_size: tuple[int, int] = (0, 0)  # (w, h)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "detections": [d.to_dict() for d in self.detections],
            "inference_ms": round(self.inference_ms, 2),
            "mode": self.mode,
            "model_name": self.model_name,
            "image_size": list(self.image_size),
            "error": self.error,
        }


# COCO classes that plausibly correspond to retail products in baseline mode.
PRODUCT_LIKE_CLASSES = {
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog",
    "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed",
    "book", "keyboard", "mouse", "remote", "cell phone", "tv", "refrigerator",
    "book", "teddy bear", "hair drier", "toothbrush", "sports ball",
}


class ProductDetector:
    """Runs detection on BGR numpy frames."""

    def __init__(self, settings: Settings, model_manager: ModelManager | None = None) -> None:
        self.settings = settings
        self.model_manager = model_manager or ModelManager(settings)
        self._infer_lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    @property
    def info(self) -> ModelInfo:
        return self.model_manager.info

    def status(self) -> dict:
        return self.model_manager.info.to_status_dict()

    def ensure_loaded(self) -> ModelInfo:
        info = self.model_manager.info
        if not info.message and not info.available:
            info = self.model_manager.load()
        return info

    def load_mode(self, mode: str) -> ModelInfo:
        return self.model_manager.load(mode, force=True)

    # ------------------------------------------------------------------ inference
    def detect(self, image_bgr, conf_threshold: float | None = None) -> DetectionResult:
        """Detect objects in a BGR ``numpy.ndarray`` image.

        Returns an empty result with ``error`` set when no model is available —
        callers decide how to surface that (never raises for missing weights).
        """
        info = self.model_manager.info
        import cv2  # local import: keep module import light

        if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
            return DetectionResult(
                mode=info.mode, model_name=info.model_name, error="Empty frame."
            )

        if not info.available or self.model_manager.model is None:
            return DetectionResult(
                mode=info.mode,
                model_name=info.model_name,
                error=info.message or "Model not loaded.",
            )

        h, w = image_bgr.shape[:2]
        conf = self.settings.confidence_threshold if conf_threshold is None else conf_threshold
        imgsz = min(640, max(320, ((max(w, h) + 31) // 32) * 32))

        started = time.perf_counter()
        try:
            with self._infer_lock:
                preds = self.model_manager.model.predict(
                    source=image_bgr,
                    conf=conf,
                    imgsz=imgsz,
                    verbose=False,
                    device="cpu",
                )
        except Exception as exc:  # noqa: BLE001
            return DetectionResult(
                mode=info.mode,
                model_name=info.model_name,
                image_size=(w, h),
                error=f"Inference failed: {exc}",
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        detections: list[Detection] = []
        if preds:
            result = preds[0]
            boxes = getattr(result, "boxes", None)
            if boxes is not None and len(boxes):
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                clss = boxes.cls.cpu().numpy().astype(int)
                names = result.names or info.classes
                for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                    label = str(names.get(int(k), int(k))) if isinstance(names, dict) else str(k)
                    det = Detection(
                        x1=int(x1),
                        y1=int(y1),
                        x2=int(x2),
                        y2=int(y2),
                        label=label,
                        confidence=float(c),
                        class_id=int(k),
                    ).clip(w, h)
                    if det.width > 2 and det.height > 2:
                        detections.append(det)

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return DetectionResult(
            detections=detections,
            inference_ms=elapsed_ms,
            mode=info.mode,
            model_name=info.model_name,
            image_size=(w, h),
        )

    def is_product_like(self, det: Detection) -> bool:
        """True when a baseline detection plausibly represents an item for sale."""
        return det.label.lower() in PRODUCT_LIKE_CLASSES


def annotate_frame(image_bgr, detections: list[Detection], product_labels: dict[str, str] | None = None):
    """Draw boxes + labels on a copy of the frame. Returns the annotated image."""
    import cv2

    annotated = image_bgr.copy()
    for det in detections:
        colour = (80, 220, 100) if (product_labels or {}).get(det.label) else (60, 180, 255)
        cv2.rectangle(annotated, (det.x1, det.y1), (det.x2, det.y2), colour, 2)
        text = f"{det.label} {det.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        y = max(det.y1, th + 6)
        cv2.rectangle(annotated, (det.x1, y - th - 6), (det.x1 + tw + 6, y + 4), colour, -1)
        cv2.putText(
            annotated,
            text,
            (det.x1 + 3, y - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return annotated
