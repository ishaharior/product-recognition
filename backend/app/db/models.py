"""ORM models: product catalogue, scans, verification results, calibration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Product(Base):
    """A catalogue entry. Weights are in grams.

    ``expected_net_weight_g`` is the weight of contents only (excluding
    packaging). ``expected_gross_weight_g`` is the weight of the sealed,
    complete retail unit. A measured reading must only ever be compared
    against the specification of the same kind.
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), default="uncategorised")
    description: Mapped[str] = mapped_column(Text, default="")
    reference_image: Mapped[str] = mapped_column(String(500), default="")

    expected_gross_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_net_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    packaging_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_tolerance_pct: Mapped[float] = mapped_column(Float, default=10.0)
    weight_spec_kind: Mapped[str] = mapped_column(String(16), default="gross")

    # Detector class name(s) this product maps to in custom-model mode.
    model_class_names: Mapped[str] = mapped_column(String(300), default="")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    colour_variants: Mapped[list[ProductColourVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductColourVariant(Base):
    """An accepted colour for a product (used for colour compatibility checks)."""

    __tablename__ = "product_colour_variants"
    __table_args__ = (UniqueConstraint("product_id", "colour_name", name="uq_product_colour"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    colour_name: Mapped[str] = mapped_column(String(64))
    hex_value: Mapped[str] = mapped_column(String(16), default="")
    primary_variant: Mapped[bool] = mapped_column(Boolean, default=False)

    product: Mapped[Product] = relationship(back_populates="colour_variants")


class ScanRecord(Base):
    """One recognition/verification event."""

    __tablename__ = "scans"

    scan_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_label: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    estimated_colour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour_quality: Mapped[str] = mapped_column(String(32), default="unknown")
    colour_distribution_json: Mapped[str] = mapped_column(Text, default="{}")

    measured_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(8), default="g")
    weight_source: Mapped[str] = mapped_column(String(16), default="none")  # real|simulated|none
    weight_stable: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    verification_status: Mapped[str] = mapped_column(String(32), default="INSUFFICIENT_EVIDENCE")
    verification_explanation: Mapped[str] = mapped_column(Text, default="")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")

    inference_mode: Mapped[str] = mapped_column(String(16), default="baseline")
    source: Mapped[str] = mapped_column(String(16), default="live")  # live|demo
    image_ref: Mapped[str] = mapped_column(String(500), default="")
    inference_ms: Mapped[float] = mapped_column(Float, default=0.0)

    product: Mapped[Product | None] = relationship(lazy="selectin")


class SensorCalibration(Base):
    """Metadata for a sensor calibration event (never the raw secret, just data)."""

    __tablename__ = "sensor_calibrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    port: Mapped[str] = mapped_column(String(64), default="")
    scale_name: Mapped[str] = mapped_column(String(64), default="scale-1")
    calibration_factor: Mapped[float] = mapped_column(Float, default=1.0)
    reference_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_reading_at_calibration: Mapped[float | None] = mapped_column(Float, nullable=True)
    offset_g: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
