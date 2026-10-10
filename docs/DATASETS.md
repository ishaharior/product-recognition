# Datasets

No dataset is required to run the application — demo mode and the baseline model
work out of the box. A dataset is only needed to **train a custom product model**
(see [MODEL_TRAINING.md](MODEL_TRAINING.md)).

Everything below is opt-in: no script in this repository downloads anything by itself.

## Supported annotation formats

| Format | Layout | Converter support |
| ------ | ------ | ----------------- |
| YOLO | `images/*.jpg` + `labels/*.txt` (one line per object: `class cx cy w h`, normalised) | native — `inspect`/`split`/`config` work directly |
| PASCAL VOC | per-image `.xml` with `<bndbox>` | `convert --format voc` → YOLO |
| COCO | single `.json` with `images`/`annotations`/`categories` | `convert --format coco` → YOLO |

Anything else is reported as `unsupported` with a clear error — never silently ignored.

## Workflow

Run from the repository root:

```powershell
# 1. Inspect a raw dataset (image/label counts, class histogram, corrupt files)
python scripts/prepare_dataset.py inspect data/datasets/my_raw_data

# 2. Convert to the canonical YOLO layout (skip if already YOLO)
python scripts/prepare_dataset.py convert data/datasets/my_raw_data data/datasets/converted --format voc

# 3. Deterministic, leakage-free train/val(/test) split
python scripts/prepare_dataset.py split data/datasets/converted data/datasets/my_products --seed 42

# 4. Write the Ultralytics dataset.yaml used by training
python scripts/prepare_dataset.py config data/datasets/my_products data/dataset_config.yaml --names cola juice

# 5. Train (explicit, manual step — see MODEL_TRAINING.md)
python scripts/train_model.py --data data/dataset_config.yaml --dry-run
```

Prepared datasets live in `data/datasets/` (git-ignored). The backend reports what
is available at `GET /api/status` → `dataset_status`.

## Candidate public datasets

Checked against the sources below on 2026-10-09 — always re-read the licence before use.

### Freiburg Groceries
- **What:** 5 000 images of 256×256 px, 25 food classes (Jund et al., 2016).
- **Repo/download:** [`PhilJd/freiburg_groceries_dataset`](https://github.com/PhilJd/freiburg_groceries_dataset) — download via the included `download_dataset.py`; fixed 5-fold splits included.
- **Licence:** the repository ships **no explicit LICENSE file**; it is published for research use. Confirm terms with the authors before redistribution.
- **Good for:** a quick, clean multiclass baseline for groceries-style products.

### RPC — Retail Product Checkout
- **What:** large fine-grained retail checkout benchmark, 200 product categories:
  53 739 single-product training images, 6 000 validation + 24 000 multi-product checkout images.
- **Download:** [Kaggle — "The Retail Product Checkout dataset"](https://www.kaggle.com/diyer22/retail-product-checkout-dataset) (≈15 GB; Baidu mirror on the project page).
- **Licence:** **CC BY-NC-SA 4.0**; project page states free for academic usage, other purposes require contacting the authors.
- **Good for:** realistic multi-product clutter, SKU-level evaluation.

### Products-10K
- **What:** 10 000 SKUs from JD.com, ≈190 000 manually labelled images with a hierarchical label graph (Bai et al., 2020).
- **Download:** [products-10k.github.io/challenge.html](https://products-10k.github.io/challenge.html) (OneDrive / JD Pan) with labels.
- **Licence:** **non-commercial research and educational purposes only**, with usage terms on the download page (incl. employer-acceptance clause for for-profit employees).
- **Good for:** large-scale SKU recognition research.

### Capturing your own station data (recommended for real deployments)
Your station's actual products under its actual lighting are usually the best training
data: place each product on the stage, capture 20–50 images per SKU from varied angles,
and label with any YOLO-format tool (e.g. Label Studio, Roboflow, CVAT — external tools,
not vendored here). Mix in negative samples (empty stage, unrelated objects).

## Honesty notes

- The comparison harness (`scripts/compare_verification.py`) generates **synthetic**
  evaluation rows when given `--generate-sample`; its output is labelled
  `SIMULATED INPUT — NOT a real experimental result` for that reason.
- Metrics reported by `scripts/validate_model.py` describe **that run on that split only**.
