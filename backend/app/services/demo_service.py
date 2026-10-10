"""Deterministic demo mode.

Runs without a camera, model weights, sensor or dataset. It produces a fixed
cycle of simulated scan events (verified / mismatch / unknown / low-confidence)
plus synthetic annotated frames, all clearly labelled as simulated data.

Nothing here is ever presented as a real measurement: every event carries
``source="demo"`` and weight source ``"simulated"``.
"""

from __future__ import annotations

import base64
import random
import threading
import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class DemoEvent:
    seq: int
    index: int
    sku: str  # "" when the object is intentionally not in the catalogue
    label: str
    confidence: float
    box: tuple[int, int, int, int]
    colour_name: str
    colour_hex: str
    weight_g: float
    expected_weight_g: float | None
    scenario: str  # verified | weight_mismatch | colour_mismatch | unknown | low_confidence
    note: str
    frame_b64: str = ""
    created_at: float = field(default_factory=time.time)

    @property
    def colour_distribution(self) -> dict[str, float]:
        return {self.colour_name: 0.78, "grey": 0.12, "white": 0.10}


# (sku, label, confidence, colour_name, colour_hex, base_weight_g, scenario, note)
_SEQUENCE: list[tuple] = [
    ("DEMO-001", "demo cola can", 0.93, "red", "#e63946", 355.0, "verified",
     "Simulated scan — consistent with catalogue specification."),
    ("DEMO-003", "demo potato chips", 0.88, "yellow", "#fcbf49", 165.0, "verified",
     "Simulated scan — consistent with catalogue specification."),
    ("DEMO-004", "demo mineral water", 0.91, "blue", "#457b9d", 525.0, "verified",
     "Simulated scan — consistent with catalogue specification."),
    ("", "mystery object", 0.64, "purple", "#7b5ea7", 240.0, "unknown",
     "Simulated object with no catalogue entry."),
    ("DEMO-002", "demo orange juice", 0.86, "orange", "#f77f00", 952.0, "weight_mismatch",
     "Simulated underweight reading (outside tolerance)."),
    ("DEMO-005", "demo coffee box", 0.90, "blue", "#457b9d", 300.0, "colour_mismatch",
     "Simulated colour at odds with the catalogue reference."),
    ("DEMO-001", "demo cola can", 0.31, "red", "#e63946", 355.0, "low_confidence",
     "Simulated weak detection — evidence insufficient."),
]

_FRAME_W, _FRAME_H = 640, 400


def _hex_to_bgr(hex_value: str) -> tuple[int, int, int]:
    hex_value = hex_value.lstrip("#")
    if len(hex_value) != 6:
        return (128, 128, 128)
    r, g, b = int(hex_value[0:2], 16), int(hex_value[2:4], 16), int(hex_value[4:6], 16)
    return (b, g, r)


def render_demo_frame(label: str, colour_hex: str, confidence: float, note: str) -> str:
    """Render a synthetic product card and return it as a base64 JPEG."""
    import cv2

    img = np.zeros((_FRAME_H, _FRAME_W, 3), dtype=np.uint8)
    # deterministic background gradient
    for y in range(_FRAME_H):
        img[y, :] = (34 + y // 12, 38, 48 + y // 16)

    box = (200, 70, 440, 330)
    x1, y1, x2, y2 = box
    colour = _hex_to_bgr(colour_hex)
    cv2.rectangle(img, (x1, y1), (x2, y2), colour, -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (250, 250, 250), 2)
    # label plate
    cv2.rectangle(img, (x1 + 16, y1 + 16), (x2 - 16, y1 + 66), (20, 20, 24), -1)
    cv2.putText(img, label.upper()[:26], (x1 + 26, y1 + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 245, 245), 2, cv2.LINE_AA)
    # detection box (simulated)
    cv2.rectangle(img, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), (60, 220, 120), 2)
    cv2.putText(img, f"{label} {confidence:.2f}", (x1 - 6, y1 - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 220, 120), 2, cv2.LINE_AA)
    # explicit SIMULATED banner
    cv2.rectangle(img, (0, 0), (_FRAME_W, 42), (20, 20, 20), -1)
    cv2.putText(img, "DEMO MODE - SIMULATED DATA", (16, 29),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (40, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(img, note[:70], (16, _FRAME_H - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
    if not ok:  # pragma: no cover
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")


class DemoService:
    """Stateful demo sequencer (thread-safe)."""

    def __init__(self, tick_ms: int = 900) -> None:
        self.tick_ms = tick_ms
        self._lock = threading.Lock()
        self._active = False
        self._paused = False
        self._cursor = 0
        self._seq = 0
        self._events_total = 0
        self._frame_cache: dict[int, str] = {}

    # ------------------------------------------------------------------ state
    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def status(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "paused": self._paused,
                "tick_ms": self.tick_ms,
                "events_total": self._events_total,
                "message": (
                    "Demo sequence running — all data simulated."
                    if self._active and not self._paused
                    else "Demo paused." if self._active else "Demo inactive."
                ),
            }

    def start(self) -> dict:
        with self._lock:
            self._active = True
            self._paused = False
            return self.status_locked()

    def stop(self) -> dict:
        with self._lock:
            self._active = False
            self._paused = False
            return self.status_locked()

    def pause(self) -> dict:
        with self._lock:
            if self._active:
                self._paused = True
            return self.status_locked()

    def resume(self) -> dict:
        with self._lock:
            if self._active:
                self._paused = False
            return self.status_locked()

    def reset(self) -> dict:
        with self._lock:
            self._cursor = 0
            self._seq = 0
            self._events_total = 0
            self._frame_cache.clear()
            return self.status_locked()

    def status_locked(self) -> dict:
        return {
            "active": self._active,
            "paused": self._paused,
            "tick_ms": self.tick_ms,
            "events_total": self._events_total,
            "message": (
                "Demo sequence running — all data simulated."
                if self._active and not self._paused
                else "Demo paused." if self._active else "Demo inactive."
            ),
        }

    # ------------------------------------------------------------------ events
    def next_event(self) -> DemoEvent | None:
        """Advance the deterministic sequence and return the next event."""
        with self._lock:
            if not self._active or self._paused:
                return None
            entry = _SEQUENCE[self._cursor % len(_SEQUENCE)]
            self._cursor += 1
            self._seq += 1
            self._events_total += 1
            index = (self._cursor - 1) % len(_SEQUENCE)
            seq = self._seq

        (sku, label, confidence, colour_name, colour_hex, base_weight, scenario, note) = entry
        rng = random.Random(index * 977 + 13)
        weight = round(base_weight + rng.uniform(-1.2, 1.2), 1)
        expected = self._expected_weight(sku, base_weight, scenario)

        if index not in self._frame_cache:
            self._frame_cache[index] = render_demo_frame(label, colour_hex, confidence, note)
        frame = self._frame_cache[index]

        return DemoEvent(
            seq=seq,
            index=index,
            sku=sku,
            label=label,
            confidence=confidence,
            box=(200, 70, 440, 330),
            colour_name=colour_name,
            colour_hex=colour_hex,
            weight_g=weight,
            expected_weight_g=expected,
            scenario=scenario,
            note=note,
            frame_b64=frame,
        )

    @staticmethod
    def _expected_weight(sku: str, base_weight: float, scenario: str) -> float | None:
        if scenario == "unknown":
            return None
        return base_weight
