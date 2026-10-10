# `data/`

| File / dir          | Purpose                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `product_specs.csv` | Product catalogue seeding file (SKUs, weights, accepted colours). Loaded at backend startup for any SKU not already in the database. |
| `dataset_config.yaml` | Ultralytics `dataset.yaml` used by `scripts/train_model.py`. Edit or regenerate after preparing a dataset. |
| `sample/`           | Sample images used by demo/synthetic frames and tooling.                                     |
| `datasets/`         | Prepared training datasets (created by `scripts/prepare_dataset.py`, git-ignored).           |
| `experiment_sample.csv` / `experiment_report.json` | Output of `scripts/compare_verification.py` (vision-only vs multimodal experiment harness). |

## `product_specs.csv` columns

| Column | Required | Notes |
| ------ | -------- | ----- |
| `sku` | yes | Unique stock-keeping unit. Skipped if the SKU already exists in the DB. |
| `name` | yes | Display name. |
| `category` | no | Defaults to `uncategorised`. |
| `description` | no | |
| `expected_gross_weight_g` | no | Gross weight including packaging. |
| `expected_net_weight_g` | no | Net product weight. |
| `packaging_weight_g` | no | Used to reconstruct gross weight when only net is specified. |
| `weight_tolerance_pct` | no | Default `10.0`. |
| `weight_spec_kind` | no | `gross` (default) or `net` — which spec the scale reading is compared against. |
| `colours` | no | `name#hex` pairs separated by `\|`, e.g. `blue#457b9d\|white#f5f5f5`. First entry is the primary variant. |
| `model_class_names` | no | Detector labels mapped to this SKU, comma-separated. COCO class names (e.g. `bottle`) work with the baseline model. |
