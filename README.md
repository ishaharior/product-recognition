# Smart Product Station

Live product recognition station: a FastAPI backend does YOLO object detection,
colour analysis and weight-sensor fusion, applies **explainable verification rules**
per product spec, and stores scan history in SQLite. A React dashboard shows live
frames, detections, verification results, catalogue and metrics.

Everything runs **without hardware and without a custom model**: demo mode generates
deterministic simulated scans, and the baseline model ships with the repository.

## Features

- **Live scanning** — browser camera frames → WebSocket `/ws/scan` → YOLO detections
  with a warmed model (~100 ms/frame after warm-up), or fully simulated demo frames.
- **Colour analysis** — HSV colour naming + CIELAB ΔE76 similarity to each product's
  accepted colour variants; reports when the result is unreliable.
- **Weight sensor** — mock sensor by default; real HX711 hardware over serial with
  tare, calibration, stability detection (`docs/HARDWARE_SETUP.md`).
- **Explainable verification** — every scan carries per-check evidence and one of:
  `VERIFIED`, `REVIEW_REQUIRED`, `UNKNOWN_PRODUCT`, `WEIGHT_MISMATCH`,
  `COLOUR_MISMATCH`, `SENSOR_UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`.
- **History** — SQLite persistence, filters, CSV export, Recharts analytics.
- **Catalogue** — CRUD API + UI; seeded from demo SKUs and `data/product_specs.csv`.
- **Dataset & training tooling** — inspect/convert/split/configure datasets, train and
  validate a custom YOLO model (opt-in scripts, never automatic).

## Requirements

- Windows 10/11 (commands below are PowerShell; the code is cross-platform)
- Python **3.11+** (tested on 3.12)
- Node.js **18+** (tested on 26) with npm
- ~2 GB disk for PyTorch + model weights; webcam for live scanning (optional)

## Setup (Windows PowerShell)

```powershell
cd "F:\Github Projects\distance-mapping"

# 1. Python environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. PyTorch — CPU wheels (use the CUDA index on a GPU machine, see requirements.txt)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Backend dependencies
pip install -r requirements.txt

# 4. Frontend dependencies
cd frontend
npm install
cd ..

# 5. (optional) local configuration
Copy-Item .env.example .env
```

## Running

### Backend — <http://127.0.0.1:8000>

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Swagger UI: <http://127.0.0.1:8000/docs> · Health: <http://127.0.0.1:8000/api/health>

### Frontend (dev server) — <http://localhost:5173>

```powershell
cd frontend
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to port 8000 (`frontend/vite.config.ts`).

### Both at once (optional convenience)

```powershell
.venv\Scripts\Activate.ps1
python scripts/run_dev.py
```

Ctrl+C stops both. The separate commands above are the primary, always-supported way.

### Single-origin (backend serves the built dashboard)

```powershell
cd frontend; npm run build; cd ..
python -m uvicorn app.main:app --app-dir backend --port 8000
# open http://127.0.0.1:8000/
```

## Demo mode

Demo mode needs no camera, sensor, weights or dataset. Activate it **one of three ways**:

1. **UI** — on the Overview page use **Demo controls → Start** (events stream
   automatically, frames are labelled `DEMO MODE - SIMULATED DATA`).
2. **API** — `Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/start`
   (also `.../demo/pause`, `/resume`, `/stop`, `/reset`).
3. **Model-free startup** — `$env:INFERENCE_MODE = "demo"` before launching the
   backend: the YOLO model is never loaded (the sequence itself is still started
   with option 1 or 2).

The deterministic cycle demonstrates: two verified scans, an unknown object, a
weight mismatch, a colour mismatch and a low-confidence review — with the matching
statuses appearing in History.

## Inference modes

| Mode | When to use | How |
| ---- | ----------- | --- |
| `baseline` (default) | COCO-class objects (bottle, cup, …) with the bundled `models/yolo11n.pt` | — |
| `custom` | your trained product model | `$env:INFERENCE_MODE = "custom"` and `$env:CUSTOM_WEIGHTS = "runs/train/<name>/weights/best.pt"` |
| `demo` | no model at all | `$env:INFERENCE_MODE = "demo"` |

Persistent settings go in `.env` (copy of `.env.example`).

## Testing

```powershell
# Backend — unit + API tests (uses its own SQLite file)
.venv\Scripts\Activate.ps1
python -m pytest backend/tests -q

# Frontend — typecheck, unit tests, production build
cd frontend
npm run typecheck
npm test
npm run build
```

## Custom model training

```powershell
python scripts/prepare_dataset.py inspect data/datasets/my_raw_data
python scripts/prepare_dataset.py convert data/datasets/my_raw_data data/datasets/converted --format voc   # YOLO datasets skip this
python scripts/prepare_dataset.py split   data/datasets/converted data/datasets/my_products --seed 42
python scripts/prepare_dataset.py config  data/datasets/my_products data/dataset_config.yaml --names cola juice

python scripts/train_model.py --data data/dataset_config.yaml --dry-run          # preview
python scripts/train_model.py --data data/dataset_config.yaml --name station-v1  # train (explicit, slow on CPU)
python scripts/validate_model.py --weights runs/train/station-v1/weights/best.pt --data data/dataset_config.yaml --split val
```

Then set `INFERENCE_MODE=custom` + `CUSTOM_WEIGHTS` (see modes table). Full guide:
[docs/MODEL_TRAINING.md](docs/MODEL_TRAINING.md) · datasets & licences:
[docs/DATASETS.md](docs/DATASETS.md).

## Weighing hardware (optional)

Mock sensor is the default. For a real HX711 load cell: flash
`firmware/scale_controller/`, wire it (SCK→D4, DOUT→D5), set
`SENSOR_BACKEND=serial` and `SENSOR_PORT=COM3` in `.env`, then:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/sensor/tare
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/sensor/calibrate `
    -ContentType 'application/json' -Body '{"reference_weight_g": 100, "samples": 20}'
```

Full guide incl. wiring and protocol: [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md).

## API surface (summary)

| Endpoint | Purpose |
| -------- | ------- |
| `GET /api/health`, `GET /api/status` | liveness; mode/model/sensor/dataset status |
| `GET/POST /api/products`, `GET/PUT/DELETE /api/products/{id}` | catalogue CRUD |
| `GET /api/scans`, `GET /api/scans/export.csv`, `GET /api/scans/{id}` | history + CSV export |
| `GET /api/metrics` | aggregate dashboard metrics |
| `POST /api/demo/{start,stop,pause,resume,reset}` | demo controls |
| `GET /api/sensor/{status,reading}`, `POST /api/sensor/{tare,calibrate}` | sensor |
| `WS /ws/scan` | camera frames in → detections/verification out |

## Repository layout

```
backend/   FastAPI app (routes, services, DB)      src/       vision, sensors, verification, datasets
frontend/  React + TS + Vite dashboard             scripts/   dataset/training/validation/launcher tools
firmware/  HX711 scale controller sketch           data/      product specs, dataset config, samples
models/    YOLO weights                            docs/      architecture, datasets, hardware, training
```

## Documentation

[docs/README.md](docs/README.md) — ARCHITECTURE · DATASETS · MODEL_TRAINING ·
HARDWARE_SETUP · TROUBLESHOOTING (webcam, serial ports, missing weights, CORS, ports).

## Known limitations (honest summary)

- **Hardware untested on real devices** — the HX711 serial path and firmware are
  implemented but automated tests cover the *mock* sensor only; no hardware test run
  is claimed.
- **Baseline model ≠ SKU recognition** — `yolo11n.pt` detects COCO classes; custom
  SKUs require training (workflow above).
- **Synthetic experiment data** — `scripts/compare_verification.py --generate-sample`
  output is explicitly labelled *simulated*; it demonstrates the harness, not real
  product accuracy.
- **CPU-first** — inference and training run on CPU by default; GPU is opt-in.
- Windows/macOS paths are untested beyond Windows in this checkout.
