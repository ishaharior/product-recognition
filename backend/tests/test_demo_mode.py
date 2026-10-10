"""Demo mode: controls, determinism, and simulated-data labelling."""

from __future__ import annotations


def test_demo_controls(client):
    assert client.post("/api/demo/start").json()["demo"]["active"] is True
    assert client.post("/api/demo/pause").json()["demo"]["paused"] is True
    assert client.post("/api/demo/resume").json()["demo"]["paused"] is False
    reset = client.post("/api/demo/reset").json()
    assert reset["ok"] is True
    assert reset["demo"]["events_total"] == 0
    assert client.post("/api/demo/stop").json()["demo"]["active"] is False


def test_demo_sequence_is_deterministic(client, app_state):
    def sequence():
        app_state.demo.stop()
        app_state.demo.reset()
        app_state.demo.start()
        items = []
        for _ in range(7):
            event = app_state.demo.next_event()
            result = app_state.scans.process_demo_event(event)
            items.append(
                (
                    event.sku,
                    event.label,
                    round(event.confidence, 3),
                    event.colour_name,
                    event.scenario,
                    result.scan.verification_status if result.scan else None,
                )
            )
        app_state.demo.stop()
        return items

    first = sequence()
    second = sequence()
    assert first == second
    scenarios = {row[4] for row in first}
    assert {"verified", "unknown", "weight_mismatch", "colour_mismatch", "low_confidence"} <= scenarios


def test_demo_frames_are_labelled_simulated(client, app_state):
    app_state.demo.start()
    app_state.demo.reset()
    event = app_state.demo.next_event()
    assert event.frame_b64, "demo events must carry a synthetic frame"
    assert event.note.startswith("Simulated")

    result = app_state.scans.process_demo_event(event)
    assert result.scan is not None
    assert result.scan.source == "demo"
    assert result.scan.weight_source == "simulated"
    assert any("SIMULATED" in w.upper() or "DEMO" in w.upper() for w in result.warnings)


def test_demo_stop_halts_events(client, app_state):
    app_state.demo.start()
    app_state.demo.stop()
    assert app_state.demo.next_event() is None


def test_ws_rejects_frames_during_demo(client, app_state):
    app_state.demo.start()
    with client.websocket_connect("/ws/scan") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        ws.send_json({"type": "frame", "image": ""})
        reply = ws.receive_json()
        assert reply["type"] == "status"
        assert "demo" in reply["message"].lower()
    app_state.demo.stop()


def test_ws_unknown_message_type(client):
    with client.websocket_connect("/ws/scan") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "teleport"})
        reply = ws.receive_json()
        assert reply["type"] == "error"


def test_ws_ping_pong(client):
    with client.websocket_connect("/ws/scan") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
