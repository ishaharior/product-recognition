# `models/`

- **`yolo11n.pt`** — Ultralytics YOLO11n baseline weights. Present in this checkout;
  if missing, Ultralytics downloads it automatically on first model load
  (network required once). Used when `INFERENCE_MODE=baseline`.
- **Custom weights** — place trained weights here (e.g. `models/station-v1/best.pt`)
  and point the backend at them:

  ```powershell
  $env:INFERENCE_MODE = "custom"
  $env:CUSTOM_WEIGHTS = "models/station-v1/best.pt"
  ```

  Weights referenced by `CUSTOM_WEIGHTS` may also live at `runs/train/<name>/weights/best.pt`
  (relative to the repository root or absolute).

See `docs/MODEL_TRAINING.md` for the training workflow.
