"""Model manager: custom-missing errors, baseline resolution, detector guards."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from app.core.config import load_settings
from src.vision.detector import Detection, ProductDetector, annotate_frame
from src.vision.model_manager import ModelManager


def test_custom_weights_missing_gives_informative_message(tmp_path):
    settings = dataclasses.replace(
        load_settings(),
        inference_mode="custom",
        custom_weights=str(tmp_path / "missing_product_model.pt"),
    )
    manager = ModelManager(settings)
    info = manager.load("custom")
    assert info.available is False
    assert info.weights_present is False
    assert "train" in info.message.lower() or "weights" in info.message.lower()
    assert "baseline" in info.message.lower() or "demo" in info.message.lower()
    assert manager.model is None


def test_custom_weights_empty_path(tmp_path):
    settings = dataclasses.replace(load_settings(), inference_mode="custom", custom_weights="")
    manager = ModelManager(settings)
    info = manager.load("custom")
    assert info.available is False
    assert "not configured" in info.message


def test_resolve_weights_baseline_found_in_models_dir():
    settings = load_settings()
    manager = ModelManager(settings)
    resolved = manager.resolve_weights("baseline")
    # models/yolo11n.pt ships with the repo working copy after first download
    if (settings.models_dir / settings.baseline_weights).exists():
        assert resolved is not None and resolved.name.endswith(".pt")
    else:
        assert resolved is None  # ultralytics will fetch on demand instead


def test_resolve_weights_custom(tmp_path):
    weights = tmp_path / "custom.pt"
    weights.write_bytes(b"stub")
    settings = dataclasses.replace(load_settings(), custom_weights=str(weights))
    manager = ModelManager(settings)
    assert manager.resolve_weights("custom") == weights


def test_detector_reports_error_when_unavailable(tmp_path):
    settings = dataclasses.replace(
        load_settings(), inference_mode="custom", custom_weights=str(tmp_path / "nope.pt")
    )
    detector = ProductDetector(settings)
    detector.model_manager.load("custom")
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    result = detector.detect(image)
    assert result.error
    assert result.detections == []
    assert "weights" in result.error.lower() or "model" in result.error.lower()


def test_detector_empty_frame_guard():
    detector = ProductDetector(load_settings())
    result = detector.detect(np.zeros((0, 0, 3), dtype=np.uint8))
    assert result.error == "Empty frame."


def test_detection_geometry():
    det = Detection(x1=-10, y1=-5, x2=50, y2=60, label="bottle", confidence=0.8, class_id=39)
    clipped = det.clip(100, 100)
    assert clipped.x1 == 0 and clipped.y1 == 0
    assert clipped.width == 50 and clipped.height == 60
    assert clipped.area == 3000
    assert clipped.cx == 25
    d = det.to_dict()
    assert d["label"] == "bottle" and d["confidence"] == 0.8


def test_annotate_frame_returns_image():
    image = np.full((120, 160, 3), 40, dtype=np.uint8)
    det = Detection(10, 10, 80, 90, "cup", 0.91, 41)
    out = annotate_frame(image, [det], {"cup": "Demo Cup"})
    assert out.shape == image.shape
    assert not np.array_equal(out, image)  # something was drawn


def test_product_like_labels():
    settings = load_settings()
    detector = ProductDetector(settings)
    assert detector.is_product_like(Detection(0, 0, 10, 10, "bottle", 0.5))
    assert not detector.is_product_like(Detection(0, 0, 10, 10, "traffic light", 0.5))
