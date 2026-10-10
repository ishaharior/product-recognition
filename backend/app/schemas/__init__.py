"""Pydantic request/response schemas — the public API contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VerificationStatus = Literal[
    "VERIFIED",
    "REVIEW_REQUIRED",
    "UNKNOWN_PRODUCT",
    "WEIGHT_MISMATCH",
    "COLOUR_MISMATCH",
    "SENSOR_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE",
]

InferenceMode = Literal["baseline", "custom", "demo"]
WeightSource = Literal["real", "simulated", "none"]


# --------------------------------------------------------------------------- health/status
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "smart-product-station"
    version: str = "1.0.0"
    time: datetime


class ModelStatus(BaseModel):
    mode: InferenceMode
    available: bool
    model_name: str = ""
    weights_path: str = ""
    weights_present: bool = False
    classes: list[str] = Field(default_factory=list)
    class_count: int = 0
    message: str = ""
    is_generic_detector: bool = True


class SensorStatus(BaseModel):
    backend: Literal["mock", "serial", "disabled"]
    connected: bool
    calibrated: bool
    simulated: bool
    port: str | None = None
    last_reading_g: float | None = None
    stable: bool = False
    message: str = ""


class DatasetStatus(BaseModel):
    config_path: str
    config_exists: bool
    datasets_dir: str
    prepared_datasets: list[str] = Field(default_factory=list)
    message: str = ""


class DemoStatus(BaseModel):
    active: bool = False
    paused: bool = False
    tick_ms: int = 900
    events_total: int = 0
    message: str = ""


class StatusResponse(BaseModel):
    inference: ModelStatus
    sensor: SensorStatus
    demo: DemoStatus
    dataset: DatasetStatus
    camera_expected: bool = True
    fps_limit: int = 8
    frame_max_size: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- products
class ColourVariantIn(BaseModel):
    colour_name: str = Field(min_length=1, max_length=64)
    hex_value: str = Field(default="", max_length=16)
    primary_variant: bool = False


class ColourVariantOut(ColourVariantIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    product_id: str


class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="uncategorised", max_length=100)
    description: str = Field(default="", max_length=2000)
    reference_image: str = Field(default="", max_length=500)
    expected_gross_weight_g: float | None = Field(default=None, ge=0)
    expected_net_weight_g: float | None = Field(default=None, ge=0)
    packaging_weight_g: float | None = Field(default=None, ge=0)
    weight_tolerance_pct: float = Field(default=10.0, ge=0, le=100)
    weight_spec_kind: Literal["gross", "net"] = "gross"
    model_class_names: str = Field(default="", max_length=300)
    active: bool = True
    colour_variants: list[ColourVariantIn] = Field(default_factory=list)

    @field_validator("weight_spec_kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ("gross", "net"):
            raise ValueError("weight_spec_kind must be 'gross' or 'net'")
        return v


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    description: str | None = None
    reference_image: str | None = None
    expected_gross_weight_g: float | None = Field(default=None, ge=0)
    expected_net_weight_g: float | None = Field(default=None, ge=0)
    packaging_weight_g: float | None = Field(default=None, ge=0)
    weight_tolerance_pct: float | None = Field(default=None, ge=0, le=100)
    weight_spec_kind: Literal["gross", "net"] | None = None
    model_class_names: str | None = None
    active: bool | None = None
    colour_variants: list[ColourVariantIn] | None = None


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    active: bool
    created_at: datetime
    updated_at: datetime
    colour_variants: list[ColourVariantOut] = Field(default_factory=list)


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int


# --------------------------------------------------------------------------- scans
class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scan_id: str
    timestamp: datetime
    product_id: str | None = None
    product_name: str | None = None
    product_sku: str | None = None
    detected_label: str
    confidence: float
    estimated_colour: str | None = None
    colour_quality: str
    colour_distribution: dict[str, float] = Field(default_factory=dict)
    measured_weight_g: float | None = None
    weight_unit: str
    weight_source: WeightSource = "none"
    weight_stable: bool = False
    expected_weight_g: float | None = None
    weight_delta_pct: float | None = None
    verification_status: VerificationStatus = "INSUFFICIENT_EVIDENCE"
    verification_explanation: str = ""
    warnings: list[str] = Field(default_factory=list)
    inference_mode: InferenceMode = "baseline"
    source: Literal["live", "demo"] = "live"
    image_ref: str = ""
    inference_ms: float = 0.0


class ScanListResponse(BaseModel):
    items: list[ScanOut]
    total: int
    limit: int
    offset: int


class ScanFilters(BaseModel):
    product_id: str | None = None
    status: VerificationStatus | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None


# --------------------------------------------------------------------------- metrics
class StatusCount(BaseModel):
    status: str
    count: int


class MetricsResponse(BaseModel):
    total_scans: int
    unique_products: int
    verified_count: int
    review_count: int
    mismatch_count: int
    unknown_count: int
    simulated_weight_count: int
    real_weight_count: int
    by_status: list[StatusCount]
    scans_over_time: list[dict[str, Any]]  # [{date, count}]
    top_products: list[dict[str, Any]]  # [{name, count}]


# --------------------------------------------------------------------------- sensor
class TareResponse(BaseModel):
    ok: bool
    message: str
    sensor: SensorStatus


class CalibrateRequest(BaseModel):
    reference_weight_g: float = Field(gt=0, le=100_000)
    samples: int = Field(default=10, ge=1, le=200)


class CalibrateResponse(BaseModel):
    ok: bool
    message: str
    calibration_factor: float
    sensor: SensorStatus


class SensorReadingResponse(BaseModel):
    weight_g: float | None
    stable: bool
    source: WeightSource
    raw: float | None = None
    message: str = ""


# --------------------------------------------------------------------------- demo
class DemoControlResponse(BaseModel):
    ok: bool
    message: str
    demo: DemoStatus


# --------------------------------------------------------------------------- websocket messages
class WSClientFrame(BaseModel):
    """Message sent from browser -> backend."""

    type: Literal["frame", "ping"] = "frame"
    image: str = ""  # base64-encoded JPEG/PNG (no data: prefix)
    width: int = 0
    height: int = 0
    ts: float = 0.0
    include_annotated: bool = True


class DetectionBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    class_id: int = -1
    is_product: bool = False
    product_id: str | None = None
    product_name: str | None = None
    colour: str | None = None
    colour_distribution: dict[str, float] = Field(default_factory=dict)
    colour_quality: str = "unknown"
    weight_g: float | None = None
    weight_source: WeightSource = "none"
    weight_stable: bool = False
    expected_weight_g: float | None = None
    verification: VerificationStatus | None = None
    explanation: str = ""


class WSServerMessage(BaseModel):
    """Message sent from backend -> browser."""

    type: Literal["ready", "detection", "status", "error", "demo", "pong"] = "detection"
    seq: int = 0
    ts: float = 0.0
    inference_ms: float = 0.0
    fps: float = 0.0
    mode: InferenceMode = "baseline"
    annotated: str | None = None  # base64 JPEG of annotated frame
    boxes: list[DetectionBox] = Field(default_factory=list)
    primary: DetectionBox | None = None
    scan_id: str | None = None
    message: str = ""
    warnings: list[str] = Field(default_factory=list)
    demo: DemoStatus | None = None
