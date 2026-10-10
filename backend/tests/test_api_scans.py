"""Scan persistence, filtering, CSV export and metrics tests."""

from __future__ import annotations


def _produce_demo_scans(app_state, count: int = 7):
    app_state.demo.start()
    app_state.demo.reset()
    scans = []
    for _ in range(count):
        event = app_state.demo.next_event()
        result = app_state.scans.process_demo_event(event)
        assert result.persisted, "demo scans must persist"
        scans.append((event, result))
    app_state.demo.stop()
    return scans


def test_demo_scans_persist(client, app_state):
    scans = _produce_demo_scans(app_state)
    assert len(scans) == 7

    res = client.get("/api/scans")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 7
    assert body["limit"] == 50

    first = body["items"][0]
    assert first["source"] == "demo"
    assert first["inference_mode"] == "demo"
    assert first["weight_source"] == "simulated"
    assert first["scan_id"]


def test_scan_statuses_are_varied(client, app_state):
    scans = _produce_demo_scans(app_state)
    statuses = {r.scan.verification_status for _, r in scans}
    # The deterministic demo sequence exercises multiple decision paths.
    assert "VERIFIED" in statuses
    assert "UNKNOWN_PRODUCT" in statuses
    assert "WEIGHT_MISMATCH" in statuses
    assert "COLOUR_MISMATCH" in statuses


def test_scan_detail_and_404(client, app_state):
    _produce_demo_scans(app_state, count=1)
    scan_id = client.get("/api/scans").json()["items"][0]["scan_id"]

    res = client.get(f"/api/scans/{scan_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["scan_id"] == scan_id
    assert detail["verification_explanation"]
    assert isinstance(detail["warnings"], list)

    assert client.get("/api/scans/not-a-real-id").status_code == 404


def test_scan_filters(client, app_state):
    _produce_demo_scans(app_state)

    mismatch = client.get("/api/scans", params={"status": "WEIGHT_MISMATCH"})
    assert mismatch.status_code == 200
    assert mismatch.json()["total"] >= 1
    assert all(
        item["verification_status"] == "WEIGHT_MISMATCH" for item in mismatch.json()["items"]
    )

    empty = client.get("/api/scans", params={"status": "COLOUR_MISMATCH", "search": "zzz"})
    assert empty.json()["total"] == 0

    bad = client.get("/api/scans", params={"status": "NOT_A_STATUS"})
    assert bad.status_code == 400


def test_csv_export(client, app_state):
    _produce_demo_scans(app_state, count=3)
    res = client.get("/api/scans/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert len(lines) == 4  # header + 3 rows
    assert lines[0].startswith("scan_id,timestamp,product_sku")


def test_metrics(client, app_state):
    _produce_demo_scans(app_state)
    res = client.get("/api/metrics")
    assert res.status_code == 200
    body = res.json()
    assert body["total_scans"] == 7
    assert body["verified_count"] >= 1
    assert body["mismatch_count"] >= 1
    assert body["unknown_count"] >= 1
    assert body["simulated_weight_count"] == 7  # demo weights are simulated
    assert body["real_weight_count"] == 0
    assert body["unique_products"] >= 1
    assert body["scans_over_time"]
    assert body["top_products"]


def test_metrics_empty_database(client):
    body = client.get("/api/metrics").json()
    assert body["total_scans"] == 0
    assert body["by_status"] == []
