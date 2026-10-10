"""Product catalogue CRUD + API validation tests."""

from __future__ import annotations

PAYLOAD = {
    "sku": "UNIT-001",
    "name": "Unit Test Cereal",
    "category": "pantry",
    "description": "Test entry",
    "expected_gross_weight_g": 480.0,
    "expected_net_weight_g": 450.0,
    "packaging_weight_g": 30.0,
    "weight_tolerance_pct": 7.5,
    "weight_spec_kind": "gross",
    "model_class_names": "cereal box",
    "colour_variants": [
        {"colour_name": "orange", "hex_value": "#f77f00", "primary_variant": True},
        {"colour_name": "white", "hex_value": "#f5f5f5", "primary_variant": False},
    ],
}


def test_seed_creates_demo_products(client):
    res = client.get("/api/products")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 5
    skus = {p["sku"] for p in body["items"]}
    assert "DEMO-001" in skus


def test_create_product_roundtrip(client):
    res = client.post("/api/products", json=PAYLOAD)
    assert res.status_code == 201
    created = res.json()
    assert created["sku"] == "UNIT-001"
    assert len(created["colour_variants"]) == 2
    assert created["colour_variants"][0]["colour_name"] == "orange"

    got = client.get(f"/api/products/{created['id']}")
    assert got.status_code == 200
    assert got.json()["expected_gross_weight_g"] == 480.0


def test_duplicate_sku_rejected(client):
    assert client.post("/api/products", json=PAYLOAD).status_code == 201
    dup = client.post("/api/products", json={**PAYLOAD, "name": "Other"})
    assert dup.status_code == 400
    assert "already exists" in dup.json()["detail"]


def test_validation_errors(client):
    res = client.post("/api/products", json={"sku": "", "name": ""})
    assert res.status_code == 422

    res = client.post("/api/products", json={**PAYLOAD, "sku": "BAD", "weight_spec_kind": "tons"})
    assert res.status_code == 422

    res = client.post(
        "/api/products", json={**PAYLOAD, "sku": "BAD2", "expected_gross_weight_g": -5}
    )
    assert res.status_code == 422


def test_update_and_delete(client):
    created = client.post("/api/products", json=PAYLOAD).json()
    pid = created["id"]

    res = client.put(f"/api/products/{pid}", json={"name": "Renamed", "weight_tolerance_pct": 12})
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed"
    assert res.json()["weight_tolerance_pct"] == 12

    # SKU collision on update
    other = client.post("/api/products", json={**PAYLOAD, "sku": "UNIT-002"}).json()
    conflict = client.put(f"/api/products/{other['id']}", json={"sku": "UNIT-001"})
    assert conflict.status_code == 400

    assert client.delete(f"/api/products/{pid}").status_code == 204
    assert client.get(f"/api/products/{pid}").status_code == 404
    assert client.delete(f"/api/products/{pid}").status_code == 404


def test_search_and_filter(client):
    assert client.post("/api/products", json=PAYLOAD).status_code == 201
    res = client.get("/api/products", params={"search": "cereal"})
    assert res.json()["total"] == 1
    res = client.get("/api/products", params={"search": "zzz-no-match"})
    assert res.json()["total"] == 0
    res = client.get("/api/products", params={"category": "pantry"})
    assert res.json()["total"] >= 1


def test_missing_product_404(client):
    assert client.get("/api/products/does-not-exist").status_code == 404
