"""WebSocket endpoint: live camera frames in, detection results out."""

from __future__ import annotations

import asyncio
import base64
import functools
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.ws_manager import ConnectionManager
from app.core.runtime import AppState

logger = logging.getLogger("smart_station.ws")
router = APIRouter()


def _decode_frame(state: AppState, b64_payload: str):
    """Decode a base64 image into a BGR numpy frame (respects size limits)."""
    import cv2
    import numpy as np

    if not b64_payload:
        return None, "Empty image payload."
    raw = b64_payload.split(",", 1)[-1] if b64_payload.startswith("data:") else b64_payload
    try:
        buffer = base64.b64decode(raw, validate=False)
        arr = np.frombuffer(buffer, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001
        return None, "Could not decode image (expected base64 JPEG/PNG)."
    if image is None or image.size == 0:
        return None, "Image could not be decoded."
    h, w = image.shape[:2]
    max_w, max_h = state.settings.max_frame_width, state.settings.max_frame_height
    if w > max_w or h > max_h:
        scale = min(max_w / w, max_h / h)
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return image, None


@router.websocket("/ws/scan")
async def ws_scan(websocket: WebSocket) -> None:
    state: AppState = websocket.app.state.station
    manager: ConnectionManager = websocket.app.state.ws_manager

    await manager.connect(websocket)
    await manager.send(
        websocket,
        {
            "type": "ready",
            "mode": state.mode,
            "message": (
                "Demo mode is active — camera frames are ignored."
                if state.demo.active
                else "Scanner ready. Send frames of type 'frame'."
            ),
            "fps_limit": state.settings.max_incoming_fps,
            "demo": state.demo.status(),
        },
    )

    loop = asyncio.get_running_loop()
    busy = False
    last_processed = 0.0
    min_interval = 1.0 / max(1, state.settings.max_incoming_fps)

    try:
        while True:
            try:
                payload = await websocket.receive_json()
            except ValueError:
                await manager.send(websocket, {"type": "error", "message": "Malformed JSON."})
                continue

            mtype = payload.get("type")
            if mtype == "ping":
                await manager.send(websocket, {"type": "pong", "ts": time.time()})
                continue
            if mtype != "frame":
                await manager.send(
                    websocket,
                    {"type": "error", "message": f"Unknown message type: {mtype!r}"},
                )
                continue

            if state.scans is None:
                await manager.send(websocket, {"type": "error", "message": "Scanner not initialised."})
                continue

            if state.demo.active:
                await manager.send(
                    websocket,
                    {
                        "type": "status",
                        "message": "Demo mode active — live camera frames are ignored until demo stops.",
                        "demo": state.demo.status(),
                    },
                )
                continue

            now = time.time()
            if busy or (now - last_processed) < min_interval:
                continue  # drop frames faster than the backend can process

            image, error = _decode_frame(state, str(payload.get("image", "")))
            if error:
                await manager.send(websocket, {"type": "error", "message": error})
                continue

            include_annotated = bool(payload.get("include_annotated", True))
            busy = True
            last_processed = now
            started = time.time()
            try:
                result = await loop.run_in_executor(
                    None,
                    functools.partial(
                        state.scans.process_frame, image, include_annotated
                    ),
                )
            finally:
                busy = False

            elapsed = time.time() - started
            await manager.send(
                websocket,
                {
                    "type": "detection",
                    "seq": int(now * 1000) % 1_000_000,
                    "ts": now,
                    "inference_ms": round(result.inference_ms, 2),
                    "fps": round(1.0 / elapsed, 1) if elapsed > 0 else 0.0,
                    "mode": state.mode,
                    "annotated": result.annotated_b64,
                    "boxes": [b.model_dump() for b in result.boxes],
                    "primary": result.primary.model_dump() if result.primary else None,
                    "scan_id": result.scan.scan_id if result.scan else None,
                    "message": result.error or "",
                    "warnings": result.warnings,
                },
            )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket error")
    finally:
        await manager.disconnect(websocket)
