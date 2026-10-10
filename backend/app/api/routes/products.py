"""Product catalogue CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_state
from app.core.runtime import AppState
from app.db.database import get_db
from app.schemas import ProductCreate, ProductListResponse, ProductOut, ProductUpdate
from app.services import catalogue

router = APIRouter(prefix="/products", tags=["products"])


def _out(product) -> ProductOut:
    return ProductOut.model_validate(product)


@router.get("", response_model=ProductListResponse)
def list_products(
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    active_only: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ProductListResponse:
    items, total = catalogue.list_products(
        db, search=search, category=category, active_only=active_only,
        limit=limit, offset=offset,
    )
    return ProductListResponse(items=[_out(p) for p in items], total=total)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)) -> ProductOut:
    try:
        return _out(catalogue.get_product(db, product_id))
    except catalogue.CatalogueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate, db: Session = Depends(get_db)
) -> ProductOut:
    try:
        product = catalogue.create_product(db, payload)
    except catalogue.CatalogueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _out(product)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str, payload: ProductUpdate, db: Session = Depends(get_db)
) -> ProductOut:
    try:
        product = catalogue.update_product(db, product_id, payload)
    except catalogue.CatalogueError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _out(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, db: Session = Depends(get_db)) -> None:
    try:
        catalogue.delete_product(db, product_id)
    except catalogue.CatalogueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
