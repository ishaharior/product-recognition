"""Product catalogue: CRUD helpers, CSV seeding, ORM -> verification specs."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductColourVariant
from app.schemas import ColourVariantIn, ProductCreate, ProductUpdate
from src.verification.verifier import ProductSpec


class CatalogueError(ValueError):
    """Raised for invalid catalogue operations (mapped to HTTP 400/404)."""


# --------------------------------------------------------------------------- conversions
def product_to_spec(product: Product) -> ProductSpec:
    accepted = [(v.colour_name, v.hex_value) for v in product.colour_variants]
    class_names = [c.strip() for c in (product.model_class_names or "").split(",") if c.strip()]
    return ProductSpec(
        id=product.id,
        sku=product.sku,
        name=product.name,
        expected_gross_weight_g=product.expected_gross_weight_g,
        expected_net_weight_g=product.expected_net_weight_g,
        packaging_weight_g=product.packaging_weight_g,
        weight_tolerance_pct=product.weight_tolerance_pct,
        weight_spec_kind=product.weight_spec_kind,  # type: ignore[arg-type]
        accepted_colours=accepted,
        model_class_names=class_names,
    )


def match_product_by_label(products: list[Product], label: str) -> Product | None:
    """Map a detector label (COCO class or custom class) to a catalogue product."""
    key = (label or "").strip().lower()
    if not key:
        return None
    for product in products:
        if not product.active:
            continue
        names = [c.strip().lower() for c in (product.model_class_names or "").split(",") if c.strip()]
        if key in names:
            return product
        if key == product.sku.strip().lower():
            return product
        if key == product.name.strip().lower():
            return product
    # last resort: token match ("apple" vs "Fresh Apple")
    for product in products:
        if not product.active:
            continue
        if key in product.name.lower():
            return product
    return None


# --------------------------------------------------------------------------- queries
def list_products(
    db: Session,
    *,
    search: str | None = None,
    category: str | None = None,
    active_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[Product], int]:
    stmt = select(Product)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.category.ilike(like),
            )
        )
    if category:
        stmt = stmt.where(Product.category == category)
    if active_only:
        stmt = stmt.where(Product.active.is_(True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = (
        db.scalars(stmt.order_by(Product.name).limit(limit).offset(offset)).all()
    )
    return list(items), int(total)


def get_product(db: Session, product_id: str) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise CatalogueError(f"Product {product_id!r} not found.")
    return product


def get_product_by_sku(db: Session, sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.sku == sku))


def _apply_variants(db: Session, product: Product, variants: list[ColourVariantIn]) -> None:
    product.colour_variants.clear()
    for v in variants:
        product.colour_variants.append(
            ProductColourVariant(
                colour_name=v.colour_name.strip(),
                hex_value=v.hex_value.strip(),
                primary_variant=v.primary_variant,
            )
        )


def create_product(db: Session, payload: ProductCreate) -> Product:
    if get_product_by_sku(db, payload.sku):
        raise CatalogueError(f"SKU {payload.sku!r} already exists.")
    product = Product(
        sku=payload.sku,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        reference_image=payload.reference_image,
        expected_gross_weight_g=payload.expected_gross_weight_g,
        expected_net_weight_g=payload.expected_net_weight_g,
        packaging_weight_g=payload.packaging_weight_g,
        weight_tolerance_pct=payload.weight_tolerance_pct,
        weight_spec_kind=payload.weight_spec_kind,
        model_class_names=payload.model_class_names,
        active=payload.active,
    )
    _apply_variants(db, product, payload.colour_variants)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product_id: str, payload: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    data = payload.model_dump(exclude_unset=True)
    variants = data.pop("colour_variants", None)
    if "sku" in data and data["sku"] != product.sku:
        existing = get_product_by_sku(db, data["sku"])
        if existing is not None and existing.id != product.id:
            raise CatalogueError(f"SKU {data['sku']!r} already exists.")
    for key, value in data.items():
        setattr(product, key, value)
    if variants is not None:
        _apply_variants(db, product, [ColourVariantIn(**v) for v in variants])
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: str) -> None:
    product = get_product(db, product_id)
    db.delete(product)
    db.commit()


# --------------------------------------------------------------------------- seeding
DEMO_PRODUCTS: list[dict] = [
    {
        "sku": "DEMO-001",
        "name": "Demo Cola Can 330ml",
        "category": "beverages",
        "description": "Simulated demo product — not a real retail item.",
        "expected_gross_weight_g": 355.0,
        "packaging_weight_g": 15.0,
        "weight_tolerance_pct": 8.0,
        "weight_spec_kind": "gross",
        "colours": [("red", "#e63946")],
        "model_class_names": "demo cola can",
    },
    {
        "sku": "DEMO-002",
        "name": "Demo Orange Juice 1L",
        "category": "beverages",
        "description": "Simulated demo product — not a real retail item.",
        "expected_gross_weight_g": 1090.0,
        "packaging_weight_g": 40.0,
        "weight_tolerance_pct": 6.0,
        "weight_spec_kind": "gross",
        "colours": [("orange", "#f77f00")],
        "model_class_names": "demo orange juice",
    },
    {
        "sku": "DEMO-003",
        "name": "Demo Potato Chips 150g",
        "category": "snacks",
        "description": "Simulated demo product — not a real retail item.",
        "expected_gross_weight_g": 165.0,
        "packaging_weight_g": 12.0,
        "weight_tolerance_pct": 10.0,
        "weight_spec_kind": "gross",
        "colours": [("yellow", "#fcbf49")],
        "model_class_names": "demo potato chips",
    },
    {
        "sku": "DEMO-004",
        "name": "Demo Mineral Water 500ml",
        "category": "beverages",
        "description": "Simulated demo product — not a real retail item.",
        "expected_gross_weight_g": 525.0,
        "packaging_weight_g": 12.0,
        "weight_tolerance_pct": 5.0,
        "weight_spec_kind": "gross",
        "colours": [("blue", "#457b9d"), ("white", "#f5f5f5")],
        "model_class_names": "demo mineral water",
    },
    {
        "sku": "DEMO-005",
        "name": "Demo Coffee Box 250g",
        "category": "pantry",
        "description": "Simulated demo product — not a real retail item.",
        "expected_gross_weight_g": 300.0,
        "packaging_weight_g": 35.0,
        "weight_tolerance_pct": 9.0,
        "weight_spec_kind": "gross",
        "colours": [("brown", "#8d5a2b")],
        "model_class_names": "demo coffee box",
    },
]


def seed_demo_products(db: Session) -> int:
    """Insert demo SKUs if missing. Returns number of rows created."""
    created = 0
    for row in DEMO_PRODUCTS:
        if get_product_by_sku(db, row["sku"]) is not None:
            continue
        product = Product(
            sku=row["sku"],
            name=row["name"],
            category=row["category"],
            description=row["description"],
            expected_gross_weight_g=row["expected_gross_weight_g"],
            packaging_weight_g=row.get("packaging_weight_g"),
            weight_tolerance_pct=row.get("weight_tolerance_pct", 10.0),
            weight_spec_kind=row.get("weight_spec_kind", "gross"),
            model_class_names=row.get("model_class_names", ""),
        )
        for idx, (name, hexv) in enumerate(row.get("colours", [])):
            product.colour_variants.append(
                ProductColourVariant(
                    colour_name=name, hex_value=hexv, primary_variant=idx == 0
                )
            )
        db.add(product)
        created += 1
    if created:
        db.commit()
    return created


def seed_from_csv(db: Session, csv_path: Path) -> tuple[int, list[str]]:
    """Seed products from ``data/product_specs.csv``. Returns (created, errors)."""
    if not csv_path.exists():
        return 0, []
    created, errors = 0, []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for lineno, row in enumerate(reader, start=2):
            try:
                sku = (row.get("sku") or "").strip()
                name = (row.get("name") or "").strip()
                if not sku or not name:
                    errors.append(f"line {lineno}: missing sku/name")
                    continue
                if get_product_by_sku(db, sku) is not None:
                    continue
                variants = []
                for idx, token in enumerate((row.get("colours") or "").split("|")):
                    token = token.strip()
                    if not token:
                        continue
                    if "#" in token:
                        cname, hexv = [p.strip() for p in token.split("#", 1)]
                        hexv = "#" + hexv
                    else:
                        cname, hexv = token, ""
                    variants.append(
                        ProductColourVariant(
                            colour_name=cname,
                            hex_value=hexv,
                            primary_variant=idx == 0,
                        )
                    )
                product = Product(
                    sku=sku,
                    name=name,
                    category=(row.get("category") or "uncategorised").strip(),
                    description=(row.get("description") or "").strip(),
                    expected_gross_weight_g=_opt_float(row.get("expected_gross_weight_g")),
                    expected_net_weight_g=_opt_float(row.get("expected_net_weight_g")),
                    packaging_weight_g=_opt_float(row.get("packaging_weight_g")),
                    weight_tolerance_pct=float(row.get("weight_tolerance_pct") or 10.0),
                    weight_spec_kind=(row.get("weight_spec_kind") or "gross").strip() or "gross",
                    model_class_names=(row.get("model_class_names") or "").strip(),
                )
                for v in variants:
                    product.colour_variants.append(v)
                db.add(product)
                db.commit()
                created += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"line {lineno}: {exc}")
    return created, errors


def _opt_float(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)
