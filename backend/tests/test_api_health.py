"""API health/status endpoint tests."""

from __future__ import annotations


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "smart-product-station"


def test_status_shape(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    body = res.json()

    inference = body["inference"]
    assert set(inference) >= {
        "mode", "available", "model_name", "classes", "message", "is_generic_detector",
    }
    # PRELOAD_MODEL=false in tests: status must not silently claim availability.
    assert inference["mode"] in {"baseline", "custom", "demo"}

    sensor = body["sensor"]
    assert sensor["backend"] == "mock"
    assert sensor["simulated"] is True

    demo = body["demo"]
    assert demo["active"] is False

    assert body["dataset"]["config_path"]
    assert body["fps_limit"] >= 1
    assert len(body["frame_max_size"]) == 2


def test_api_root_lists_endpoints(client):
    res = client.get("/api")
    assert res.status_code == 200
    assert "health" in res.json()
