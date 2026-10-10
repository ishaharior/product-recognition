"""Scan history endpoints: search, detail, CSV export."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ScanRecord
from app.schemas import ScanListResponse, ScanOut
from app.services.scan_service import scan_record_to_out

router = APIRouter(prefix="/scans", tags=["scans"])

_STATUSES = {
    "VERIFIED",
    "REVIEW_REQUIRED",
    "UNKNOWN_PRODUCT",
    "WEIGHT_MISMATCH",
    "COLOUR_MISMATCH",
    "SENSOR_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE",
}


def _filtered(
    db: Session,
    product_id: str | None,
    scan_status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    search: str | None,
):
    stmt = select(ScanRecord)
    if product_id:
        stmt = stmt.where(ScanRecord.product_id == product_id)
    if scan_status:
        if scan_status not in _STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status {scan_status!r}")
        stmt = stmt.where(ScanRecord.verification_status == scan_status)
    if date_from:
        stmt = stmt.where(ScanRecord.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(ScanRecord.timestamp <= date_to)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ScanRecord.product_name.ilike(like),
                ScanRecord.product_sku.ilike(like),
                ScanRecord.detected_label.ilike(like),
                ScanRecord.scan_id.ilike(like),
            )
        )
    return stmt


@router.get("", response_model=ScanListResponse)
def list_scans(
    product_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ScanListResponse:
    stmt = _filtered(db, product_id, status_filter, date_from, date_to, search)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ScanRecord.timestamp.desc()).limit(limit).offset(offset)
    ).all()
    return ScanListResponse(
        items=[scan_record_to_out(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/export.csv", tags=["scans"])
def export_csv(
    product_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    stmt = _filtered(db, product_id, status_filter, date_from, date_to, search)
    rows = db.scalars(stmt.order_by(ScanRecord.timestamp.desc()).limit(10_000)).all()

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "scan_id", "timestamp", "product_sku", "product_name", "detected_label",
            "confidence", "estimated_colour", "colour_quality", "measured_weight_g",
            "weight_source", "weight_stable", "expected_weight_g", "weight_delta_pct",
            "verification_status", "verification_explanation", "inference_mode",
            "source", "inference_ms",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.scan_id,
                r.timestamp.isoformat(),
                r.product_sku or "",
                r.product_name or "",
                r.detected_label,
                f"{r.confidence:.4f}",
                r.estimated_colour or "",
                r.colour_quality,
                "" if r.measured_weight_g is None else f"{r.measured_weight_g:.2f}",
                r.weight_source,
                int(r.weight_stable),
                "" if r.expected_weight_g is None else f"{r.expected_weight_g:.2f}",
                "" if r.weight_delta_pct is None else f"{r.weight_delta_pct:.2f}",
                r.verification_status,
                r.verification_explanation,
                r.inference_mode,
                r.source,
                f"{r.inference_ms:.2f}",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=scan_history.csv"},
    )


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, db: Session = Depends(get_db)) -> ScanOut:
    record = db.get(ScanRecord, scan_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return scan_record_to_out(record)
