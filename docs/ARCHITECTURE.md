# Architecture

## Repository layout

```
distance-mapping/
├── backend/                 FastAPI application
│   └── app/
│       ├── api/routes/       REST routers + /ws/scan WebSocket
│       ├── core/             config (env-driven Settings), runtime (AppState)
│       ├── db/               SQLAlchemy models + SQLite session
│       ├── schemas/          Pydantic request/response models
│       └── services/         catalogue, scans, demo, metrics
├── src/                     framework-free libraries (importable without FastAPI)
│   ├── vision/              YOLO model manager, detector, colour analysis
│   ├── sensors/             HX711 serial + mock weight sensors, stability logic
│   ├── verification/        rule engine (ProductVerifier) and evidence types
│   └── datasets/            dataset inspection/conversion/split utilities
├── frontend/                React + TypeScript + Vite dashboard
├── scripts/                 dataset tools, training, validation, experiment harness
├── firmware/                Arduino/ESP32 scale controller sketch
├── data/                    product specs, dataset config, samples
├── models/                  YOLO weights (baseline + custom)
└── docs/                    this documentation
```

`src/` stays import-light (no FastAPI/SQLAlchemy imports; `Settings` only under
`TYPE_CHECKING`) so vision/sensor/verification logic is unit-testable in isolation.
`backend/app` wires those libraries into the web layer and adds the database.

## Runtime flow (live scan)

```
Browser camera ──(JPEG frames, WebSocket /ws/scan)──▶ ws.py
        │  frame decode + FPS/rate limiting
        ▼
ScanService.process_frame()          [thread-pool executor]
        ├─ ProductDetector (YOLO, warmed, max-frame 640px)   ──▶ detections[]
        ├─ analyse_colour() on the top detection region      ──▶ ColourResult (HSV name + Lab ΔE)
        ├─ WeightSensor.read() (mock | serial HX711)         ──▶ stable grams or unavailable
        ├─ ProductVerifier.verify()                          ──▶ status + per-check explanations
        └─ persist ScanRecord (SQLite, 2.5 s per-SKU cooldown)
        │
        ▼
ConnectionManager.broadcast ──▶ all dashboard clients (cards, charts, status)
REST: GET /api/scans, /api/scans/export.csv, /api/metrics, /api/status
```

**Demo mode** (`POST /api/demo/start`) replaces the camera with a deterministic
synthetic-frame ticker (`DEMO_TICK_MS` interval, fixed 7-event cycle covering
verified / unknown / weight-mismatch / colour-mismatch / low-confidence outcomes).
Frames are generated in-process; no model inference is performed, and the UI is
labelled accordingly.

## Verification engine

Pure rules in `src/verification/verifier.py` — every decision carries per-check
`Check(name, passed, detail)` evidence so the UI can explain *why*.

| Status | Meaning |
| ------ | ------- |
| `VERIFIED` | identity + confidence + colour (when compared) + weight all within tolerance |
| `REVIEW_REQUIRED` | ambiguous evidence (e.g. low-ish confidence) — manual review recommended |
| `UNKNOWN_PRODUCT` | no catalogue match for the detected label |
| `WEIGHT_MISMATCH` | stable reading outside the SKU's tolerance |
| `COLOUR_MISMATCH` | analysed colour incompatible with accepted variants |
| `SENSOR_UNAVAILABLE` | weight evidence required but no reading |
| `INSUFFICIENT_EVIDENCE` | nothing decisive to decide on |

Weight is compared against the SKU's spec kind: `gross` readings directly, `net`
spec reconstructed as net + packaging. Colour uses CIELAB ΔE76 between the analysed
region mean and each accepted variant (lab convention L×100/255, a/b−128 normalised
on both sides). Statuses are deliberately neutral wording — the system recommends
review, it does not accuse.

## Inference modes

| `INFERENCE_MODE` | Behaviour |
| ---------------- | --------- |
| `baseline` | COCO-class YOLO (`models/yolo11n.pt`); generic classes mapped to SKUs via `model_class_names` |
| `custom` | your trained weights via `CUSTOM_WEIGHTS` (clear error if the file is missing) |
| `demo` | synthetic detections only; the detector is never loaded |

## Key design decisions

- **SQLite + SQLAlchemy 2.x** for scan history — zero-setup persistence and CSV export.
- **Mock-first sensor** (`SENSOR_BACKEND=mock|serial|disabled`) so every test and demo
  runs without hardware; real serial support is the same interface.
- **WS for frames, REST for state** — frames are high-rate and one-directional;
  everything else is request/response and cacheable.
- **Lifespan initialisation** — DB seeding, model warm-up and background tickers start
  and stop with the app (no orphan threads; `preload_model=false` for tests/CI).
- **Privacy default** — `STORE_FRAMES=false`; camera images are never written to disk.
