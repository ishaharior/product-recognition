"""Aggregated metrics for the overview dashboard."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Product, ScanRecord
from app.schemas import MetricsResponse, StatusCount

_MISMATCH_STATUSES = ("WEIGHT_MISMATCH", "COLOUR_MISMATCH")


def compute_metrics(db: Session) -> MetricsResponse:
    total = db.scalar(select(func.count(ScanRecord.scan_id))) or 0

    status_rows = db.execute(
        select(ScanRecord.verification_status, func.count(ScanRecord.scan_id))
        .group_by(ScanRecord.verification_status)
        .order_by(func.count(ScanRecord.scan_id).desc())
    ).all()
    by_status = [StatusCount(status=str(s), count=int(c)) for s, c in status_rows]
    counts = {str(s): int(c) for s, c in status_rows}

    unique_products = db.scalar(
        select(func.count(func.distinct(ScanRecord.product_id))).where(
            ScanRecord.product_id.is_not(None)
        )
    ) or 0

    verified = counts.get("VERIFIED", 0)
    review = counts.get("REVIEW_REQUIRED", 0) + counts.get("INSUFFICIENT_EVIDENCE", 0)
    mismatch = sum(counts.get(s, 0) for s in _MISMATCH_STATUSES)
    unknown = counts.get("UNKNOWN_PRODUCT", 0) + counts.get("SENSOR_UNAVAILABLE", 0)

    sim_weight = db.scalar(
        select(func.count(ScanRecord.scan_id)).where(ScanRecord.weight_source == "simulated")
    ) or 0
    real_weight = db.scalar(
        select(func.count(ScanRecord.scan_id)).where(ScanRecord.weight_source == "real")
    ) or 0

    # scans per calendar day (last 30 days of activity present in the table)
    day_expr = func.date(ScanRecord.timestamp)
    time_rows = db.execute(
        select(day_expr, func.count(ScanRecord.scan_id))
        .group_by(day_expr)
        .order_by(day_expr)
        .limit(30)
    ).all()
    scans_over_time = [{"date": str(d), "count": int(c)} for d, c in time_rows]

    top_rows = db.execute(
        select(ScanRecord.product_name, func.count(ScanRecord.scan_id))
        .where(ScanRecord.product_name.is_not(None))
        .group_by(ScanRecord.product_name)
        .order_by(func.count(ScanRecord.scan_id).desc())
        .limit(6)
    ).all()
    top_products = [{"name": str(n), "count": int(c)} for n, c in top_rows]

    catalogue_count = db.scalar(select(func.count(Product.id))) or 0
    if unique_products == 0 and catalogue_count:
        # keep the UI honest: unique products counts distinct matched products
        pass

    return MetricsResponse(
        total_scans=int(total),
        unique_products=int(unique_products),
        verified_count=int(verified),
        review_count=int(review),
        mismatch_count=int(mismatch),
        unknown_count=int(unknown),
        simulated_weight_count=int(sim_weight),
        real_weight_count=int(real_weight),
        by_status=by_status,
        scans_over_time=scans_over_time,
        top_products=top_products,
    )
