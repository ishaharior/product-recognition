# Model training

The application **never trains by itself**. Training is an explicit, opt-in workflow
run from the repository root; nothing here claims a model was trained unless a real
run completed.

## End-to-end workflow

### 1. Prepare a dataset

See [DATASETS.md](DATASETS.md) for formats, converters and candidate datasets.

```powershell
python scripts/prepare_dataset.py inspect  data/datasets/my_raw_data
python scripts/prepare_dataset.py convert  data/datasets/my_raw_data data/datasets/converted --format voc   # skip for YOLO
python scripts/prepare_dataset.py split    data/datasets/converted data/datasets/my_products --seed 42
python scripts/prepare_dataset.py config   data/datasets/my_products data/dataset_config.yaml --names cola juice
```

`split` is deterministic and leakage-free (hash-based assignment of image identity,
so the same picture never lands in train *and* val).

### 2. Check the configuration (no training yet)

```powershell
python scripts/train_model.py --data data/dataset_config.yaml --dry-run
```

Prints the resolved configuration and exits.

### 3. Train

```powershell
python scripts/train_model.py --data data/dataset_config.yaml `
    --model yolo11n.pt --epochs 50 --imgsz 640 --batch 16 --name station-v1
```

- Output: `runs/train/station-v1/weights/best.pt`.
- **CPU works but is slow** (hours for small datasets); use a CUDA machine and
  `--device 0` when possible.
- Requires `torch`/`torchvision` installed for your platform (see `requirements.txt`).

### 4. Validate before trusting anything

```powershell
python scripts/validate_model.py --weights runs/train/station-v1/weights/best.pt `
    --data data/dataset_config.yaml --split val
```

Reports precision / recall / mAP50-95 **for that run on that split only** — not a
general claim about production accuracy. Optionally writes JSON with `--out`.

### 5. Load the custom weights in the station

```powershell
$env:INFERENCE_MODE = "custom"
$env:CUSTOM_WEIGHTS = "runs/train/station-v1/weights/best.pt"
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Or copy the weights into `models/` (see `models/README.md`). Restart the backend and
confirm at `GET /api/status` → `inference.mode = custom`, weights reported as loaded.

Persistent setting: put both variables in a `.env` file at the repository root
(copy `.env.example`).

## Common failure modes

| Symptom | Fix |
| ------- | --- |
| `dataset config not found` | run step 1's `config` command; `--data` must point at a real yaml |
| `ultralytics/torch unavailable` | install backend requirements + torch for your platform |
| Weights won't load in custom mode | `CUSTOM_WEIGHTS` path is relative to the repo root; check `/api/status` message |
| Low val mAP | more images per class, ensure `names` in the yaml match your training labels |
