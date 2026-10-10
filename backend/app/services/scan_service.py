"""Scan pipeline: frame -> detection -> colour -> weight -> verification -> DB."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Product, ScanRecord
from app.schemas import DetectionBox, ScanOut
from app.services import catalogue
from app.services.demo_service import DemoEvent
from src.sensors.weight_sensor import Reading, SensorError, WeightSensor
from src.vision.color_analyzer import (
    ColourResult,
    analyse_similarity_to_accepted,
    analyze_colour,
)
from src.vision.detector import Detection, ProductDetector, annotate_frame
from src.verification.verifier import (
    ColourEvidence,
    ProductVerifier,
    VerificationInput,
    WeightEvidence,
)

EMPTY_PLATFORM_G = 5.0  # readings below this = nothing on the scale
PERSIST_COOLDOWN_S = 2.5


@dataclass
class FrameResult:
    """Outcome of processing one camera frame."""

    boxes: list[DetectionBox] = field(default_factory=list)
    primary: DetectionBox | None = None
    scan: ScanOut | None = None
    annotated_b64: str | None = None
    inference_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    persisted: bool = False


def scan_record_to_out(record: ScanRecord) -> ScanOut:
    try:
        distribution = json.loads(record.colour_distribution_json or "{}")
    except json.JSONDecodeError:
        distribution = {}
    try:
        warnings = json.loads(record.warnings_json or "[]")
    except json.JSONDecodeError:
        warnings = []
    return ScanOut(
        scan_id=record.scan_id,
        timestamp=record.timestamp,
        product_id=record.product_id,
        product_name=record.product_name,
        product_sku=record.product_sku,
        detected_label=record.detected_label,
        confidence=record.confidence,
        estimated_colour=record.estimated_colour,
        colour_quality=record.colour_quality,
        colour_distribution=distribution,
        measured_weight_g=record.measured_weight_g,
        weight_unit=record.weight_unit,
        weight_source=record.weight_source,  # type: ignore[arg-type]
        weight_stable=record.weight_stable,
        expected_weight_g=record.expected_weight_g,
        weight_delta_pct=record.weight_delta_pct,
        verification_status=record.verification_status,  # type: ignore[arg-type]
        verification_explanation=record.verification_explanation,
        warnings=warnings,
        inference_mode=record.inference_mode,  # type: ignore[arg-type]
        source=record.source,  # type: ignore[arg-type]
        image_ref=record.image_ref,
        inference_ms=record.inference_ms,
    )


class ScanService:
    def __init__(
        self,
        settings: Settings,
        detector: ProductDetector,
        sensor: WeightSensor,
        verifier: ProductVerifier,
        session_factory: sessionmaker,
    ) -> None:
        self.settings = settings
        self.detector = detector
        self.sensor = sensor
        self.verifier = verifier
        self.session_factory = session_factory
        self._products: list[Product] = []
        self._products_loaded_at = 0.0
        self._last_persist_at = 0.0
        self._last_status = ""

    # ------------------------------------------------------------------ helpers
    def refresh_products(self, db: Session | None = None) -> None:
        own = db is None
        db = db or self.session_factory()
        try:
            self._products = list(
                db.scalars(select(Product).where(Product.active.is_(True))).all()
            )
            self._products_loaded_at = time.time()
        finally:
            if own:
                db.close()

    def _get_products(self, db: Session) -> list[Product]:
        if time.time() - self._products_loaded_at > 2.0 or not self._products:
            self.refresh_products(db)
        return self._products

    def _encode(self, image) -> str:
        import cv2

        ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:  # pragma: no cover
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")

    # ------------------------------------------------------------------ weight
    def read_weight(self) -> tuple[WeightEvidence | None, list[str]]:
        """Read the sensor once. Failures become warnings — never a silent
        fallback to simulated values."""
        warnings: list[str] = []
        if self.sensor.backend == "disabled" or not self.sensor.connected:
            return None, ["Weight sensor is not connected — weight not verified."]
        try:
            reading: Reading = self.sensor.read(timeout=min(1.0, self.settings.sensor_timeout_s))
        except SensorError as exc:
            return None, [f"Weight sensor error: {exc}"]
        if reading.grams is None:
            return None, ["Weight sensor returned no value."]
        source = "simulated" if self.sensor.simulated else "real"
        if source == "simulated":
            warnings.append("Weight reading is simulated (mock sensor).")
        if abs(reading.grams) < EMPTY_PLATFORM_G:
            return (
                WeightEvidence(grams=reading.grams, stable=reading.stable, source=source, empty=True),
                ["Scale reads empty — place the product on the platform."],
            )
        return WeightEvidence(grams=reading.grams, stable=reading.stable, source=source), warnings

    # ------------------------------------------------------------------ colour
    def colour_evidence_for(
        self, image, det: Detection, product: Product | None
    ) -> tuple[ColourResult | None, ColourEvidence | None, list[str]]:
        result = analyze_colour(
            image,
            (det.x1, det.y1, det.x2, det.y2),
            min_pixels=self.settings.colour_min_region_pixels,
            saturation_low=self.settings.colour_saturation_low,
            highlight_v=self.settings.colour_highlight_v,
            shadow_v=self.settings.colour_shadow_v,
        )
        warnings = list(result.warnings)
        evidence: ColourEvidence | None = None
        if product is not None and product.colour_variants:
            accepted = [(v.colour_name, v.hex_value) for v in product.colour_variants]
            similarity = analyse_similarity_to_accepted(result, accepted)
            evidence = ColourEvidence(
                name=result.name,
                hex_value=result.hex_value,
                quality=result.quality,
                reliable=result.reliable,
                similarity=similarity,
                warnings=list(result.warnings),
            )
        return result, evidence, warnings

    # ------------------------------------------------------------------ live frame
    def process_frame(self, image, include_annotated: bool = True) -> FrameResult:
        """Run the full pipeline on one BGR frame from the browser."""
        out = FrameResult()
        if image is None or getattr(image, "size", 0) == 0:
            out.error = "Empty frame."
            return out

        # Block on the first frame if the background model load is still running
        # (subsequent frames hit the already-loaded model).
        self.detector.ensure_loaded()
        det_result = self.detector.detect(image)
        out.inference_ms = det_result.inference_ms
        if det_result.error:
            out.error = det_result.error
            return out

        detections = det_result.detections
        if not detections:
            if include_annotated:
                out.annotated_b64 = self._encode(image)
            return out

        db = self.session_factory()
        try:
            products = self._get_products(db)
            primary = self._pick_primary(detections)
            weight, weight_warnings = self.read_weight()

            boxes: list[DetectionBox] = []
            for det in detections:
                is_primary = det is primary
                product = catalogue.match_product_by_label(products, det.label)
                box = DetectionBox(
                    x1=det.x1,
                    y1=det.y1,
                    x2=det.x2,
                    y2=det.y2,
                    label=det.label,
                    confidence=round(det.confidence, 4),
                    class_id=det.class_id,
                    is_product=self.detector.is_product_like(det) or product is not None,
                    product_id=product.id if product else None,
                    product_name=product.name if product else None,
                )
                if is_primary:
                    colour_result, colour_ev, colour_warnings = self.colour_evidence_for(
                        image, det, product
                    )
                    spec = catalogue.product_to_spec(product) if product else None
                    verification = self.verifier.verify(
                        VerificationInput(
                            detected_label=det.label,
                            confidence=det.confidence,
                            product=spec,
                            colour=colour_ev,
                            weight=weight,
                            mode=det_result.mode,
                            source="live",
                        )
                    )
                    box.colour = colour_result.name if colour_result else None
                    box.colour_distribution = (
                        colour_result.to_dict()["distribution"] if colour_result else {}
                    )
                    box.colour_quality = colour_result.quality if colour_result else "unknown"
                    box.weight_g = weight.grams if weight else None
                    box.weight_source = weight.source if weight else "none"
                    box.weight_stable = weight.stable if weight else False
                    box.expected_weight_g = verification.expected_weight_g
                    box.verification = verification.status
                    box.explanation = verification.explanation
                    out.warnings.extend(colour_warnings)
                    out.warnings.extend(weight_warnings)
                    out.warnings.extend(verification.warnings)

                    record = self._persist_scan(
                        db,
                        det=det,
                        product=product,
                        colour=colour_result,
                        weight=weight,
                        verification=verification,
                        mode=det_result.mode,
                        source="live",
                        inference_ms=det_result.inference_ms,
                    )
                    if record is not None:
                        out.scan = scan_record_to_out(record)
                        out.persisted = True
                    out.primary = box
                boxes.append(box)

            out.boxes = boxes
            if include_annotated:
                labels = {
                    b.label: b.product_name or ""
                    for b in boxes
                    if b.product_name
                }
                annotated = annotate_frame(image, detections, labels)
                out.annotated_b64 = self._encode(annotated)
        finally:
            db.close()

        out.warnings = _dedupe(out.warnings)
        return out

    def _pick_primary(self, detections: list[Detection]) -> Detection:
        product_like = [d for d in detections if self.detector.is_product_like(d)]
        if product_like:
            return max(product_like, key=lambda d: d.confidence * (d.area**0.5))
        return max(detections, key=lambda d: d.confidence * max(d.area, 1) ** 0.5)

    # ------------------------------------------------------------------ demo
    def process_demo_event(self, event: DemoEvent) -> FrameResult:
        """Verify and persist one simulated demo event."""
        out = FrameResult(inference_ms=0.0)
        db = self.session_factory()
        try:
            products = self._get_products(db)
            product = None
            if event.sku:
                product = next((p for p in products if p.sku == event.sku), None)
                if product is None:
                    product = catalogue.get_product_by_sku(db, event.sku)

            colour_ev = ColourEvidence(
                name=event.colour_name,
                hex_value=event.colour_hex,
                quality="good",
                reliable=True,
            )
            if product is not None and product.colour_variants:
                accepted = [(v.colour_name, v.hex_value) for v in product.colour_variants]
                from src.vision.color_analyzer import ColourResult as CR

                synthetic = CR(
                    name=event.colour_name,
                    hex_value=event.colour_hex,
                    quality="good",
                    reliable=True,
                )
                synthetic.mean_lab = _lab_from_hex(event.colour_hex)
                colour_ev.similarity = analyse_similarity_to_accepted(synthetic, accepted)

            spec = catalogue.product_to_spec(product) if product else None
            weight = WeightEvidence(
                grams=event.weight_g, stable=True, source="simulated", empty=False
            )
            verification = self.verifier.verify(
                VerificationInput(
                    detected_label=event.label,
                    confidence=event.confidence,
                    product=spec,
                    colour=colour_ev,
                    weight=weight,
                    mode="demo",
                    source="demo",
                )
            )

            x1, y1, x2, y2 = event.box
            box = DetectionBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                label=event.label,
                confidence=event.confidence,
                is_product=product is not None,
                product_id=product.id if product else None,
                product_name=product.name if product else None,
                colour=event.colour_name,
                colour_distribution=dict(event.colour_distribution),
                colour_quality="good",
                weight_g=event.weight_g,
                weight_source="simulated",
                weight_stable=True,
                expected_weight_g=verification.expected_weight_g,
                verification=verification.status,
                explanation=verification.explanation,
            )

            colour_result = ColourResult(
                name=event.colour_name,
                hex_value=event.colour_hex,
                distribution=dict(event.colour_distribution),
                quality="good",
                warnings=[],
                pixel_count=(x2 - x1) * (y2 - y1),
                reliable=True,
            )
            colour_result.mean_lab = _lab_from_hex(event.colour_hex)

            record = self._persist_scan(
                db,
                det=Detection(x1, y1, x2, y2, event.label, event.confidence, -1),
                product=product,
                colour=colour_result,
                weight=weight,
                verification=verification,
                mode="demo",
                source="demo",
                inference_ms=0.0,
            )
            out.boxes = [box]
            out.primary = box
            out.annotated_b64 = event.frame_b64
            out.warnings = _dedupe(
                ["DEMO MODE — SIMULATED DATA.", event.note, *verification.warnings]
            )
            if record is not None:
                out.scan = scan_record_to_out(record)
                out.persisted = True
        finally:
            db.close()
        return out

    # ------------------------------------------------------------------ persistence
    def _persist_scan(
        self,
        db: Session,
        *,
        det: Detection,
        product: Product | None,
        colour: ColourResult | None,
        weight: WeightEvidence | None,
        verification,
        mode: str,
        source: str,
        inference_ms: float,
    ) -> ScanRecord | None:
        """Persist a scan, rate-limited so live scanning cannot flood the DB."""
        now = time.time()
        status = verification.status
        is_demo = source == "demo"
        if not is_demo:
            if status == self._last_status and (now - self._last_persist_at) < PERSIST_COOLDOWN_S:
                return None

        record = ScanRecord(
            product_id=product.id if product else None,
            product_name=product.name if product else None,
            product_sku=product.sku if product else None,
            detected_label=det.label,
            confidence=round(det.confidence, 4),
            estimated_colour=colour.name if colour else None,
            colour_quality=colour.quality if colour else "unknown",
            colour_distribution_json=json.dumps(colour.to_dict()["distribution"] if colour else {}),
            measured_weight_g=weight.grams if weight else None,
            weight_unit="g",
            weight_source=(weight.source if weight else "none"),
            weight_stable=bool(weight.stable) if weight else False,
            expected_weight_g=verification.expected_weight_g,
            weight_delta_pct=verification.weight_delta_pct,
            verification_status=verification.status,
            verification_explanation=verification.explanation,
            warnings_json=json.dumps(_dedupe(list(verification.warnings))),
            inference_mode=mode,  # type: ignore[arg-type]
            source=source,  # type: ignore[arg-type]
            inference_ms=round(inference_ms, 2),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        self._last_persist_at = now
        self._last_status = status
        return record


def _lab_from_hex(hex_value: str) -> tuple[float, float, float]:
    from src.vision.color_analyzer import rgb_hex_to_lab

    return rgb_hex_to_lab(hex_value)


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen)
