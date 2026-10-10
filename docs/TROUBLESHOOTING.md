# Troubleshooting

## Application will not start

**`Address already in use` / port 8000 busy**
```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
# kill the owning process, or use another port:
python -m uvicorn app.main:app --app-dir backend --port 8001
```

**`ModuleNotFoundError: No module named 'app'` / `'src'`**
Always launch from the repository root (the config adds the root to `sys.path`).

**`ModuleNotFoundError: No module named 'fastapi'` (or torch, cv2, …)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # CPU wheels
pip install -r requirements.txt
```

**Backend starts but the dashboard is blank**
The frontend dev server is separate — run it (see README) at
<http://localhost:5173>. (After `npm run build`, the backend also serves
`frontend/dist/` at <http://127.0.0.1:8000>.)

## Camera / webcam

- **Permission prompt never appears** — start the scanner page over
  `http://localhost:5173` (browsers only allow camera on `localhost`/HTTPS, not
  arbitrary LAN IPs). Click **Start camera** on `/scanner`.
- **Black frame** — another app (Teams/Zoom/OBS) may hold the camera; close it.
- **No detections on live frames** — the baseline model detects *COCO* classes
  (bottle, cup, book, …), not your custom SKUs. Either position an object the
  baseline recognises, run demo mode, or train a custom model
  (see `docs/MODEL_TRAINING.md`). Status page shows which model is loaded.
- **Frame rate low** — expected: frames are capped (`MAX_INCOMING_FPS=8`) and
  downscaled to ≤640 px to keep CPU inference responsive.

## Serial / weighing hardware

- `SENSOR_PORT` not set → set `SENSOR_PORT=COM3` (Device Manager → Ports).
- `PermissionError` → close the Arduino Serial Monitor / other terminal.
- `No data within timeout` → baud must be 9600; re-check wiring; see
  `docs/HARDWARE_SETUP.md`.
- Sensor not attached at all → keep `SENSOR_BACKEND=mock` (default) or
  `SENSOR_BACKEND=disabled`; scans then report `SENSOR_UNAVAILABLE` for weight
  instead of failing.

## Model weights

- **`baseline weights not found`** — put `yolo11n.pt` in `models/`, or let
  Ultralytics download it on first load (needs network once).
- **Custom mode errors** — `CUSTOM_WEIGHTS` must be a real path (relative to the
  repo root). Check `GET /api/status` for the resolved message.
- **First scan is slow** (several seconds) — one-time model load/warm-up;
  subsequent frames are ~100 ms. Set `PRELOAD_MODEL=true` (default) to pay the
  cost at startup instead.

## CORS

- Browser says origin blocked → the frontend must run on a port listed in
  `CORS_ORIGINS` (default `http://localhost:5173,http://127.0.0.1:5173`).
  Add your origin to `.env` and restart the backend.
- Mixed ports (e.g. Vite on 5174) are the usual cause — align them.

## Demo mode

- Demo events not appearing → `POST /api/demo/start` (or the **Demo controls**
  on the overview page); watch `GET /api/status`.
- `DEMO_TICK_MS` too fast/slow → change it in `.env`.
- Want to re-run the event cycle → `POST /api/demo/reset`.

## Database / history

- Reset everything (catalogue edits, scan history):
  stop the backend, delete `backend/smart_station.db`, restart — it is recreated
  and re-seeded from `data/product_specs.csv` + demo SKUs.
- Tests write to `backend/test_smart_station.db` (set by `conftest.py`), not the
  development database.

## Tests

```powershell
# backend (from repo root)
python -m pytest backend/tests -q

# frontend
cd frontend
npm run typecheck
npm test
npm run build
```

- Tests slow on first run (~40 s): the YOLO model loads once per session; a
  `PRELOAD_MODEL=false` is already set in test env.
- `StarletteDeprecationWarning: httpx ... testclient` is informational, not a failure.
