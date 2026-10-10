"""Train a custom product YOLO model (opt-in; NEVER runs automatically).

Examples (run from the repository root):

    # print the resolved configuration without training
    python scripts/train_model.py --data data/dataset_config.yaml --dry-run

    # train 60 epochs on CPU (slow — prefer a GPU machine for real runs)
    python scripts/train_model.py --data data/dataset_config.yaml \
        --model yolo11n.pt --epochs 60 --imgsz 640 --batch 16 --name station-v1

After training, point the backend at the best weights:

    set CUSTOM_WEIGHTS=runs/train/station-v1/weights/best.pt   # PowerShell: $env:CUSTOM_WEIGHTS=...
    set INFERENCE_MODE=custom

and restart the backend. The application does NOT train by itself and does NOT
claim a model is trained unless a real run completed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="dataset.yaml produced by prepare_dataset.py config")
    parser.add_argument("--model", default="yolo11n.pt", help="base weights (yolo11n.pt, yolo11s.pt, or a path)")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--name", default="smart-station-run", help="run directory name under --out")
    parser.add_argument("--out", default="runs/train", help="parent directory for training runs")
    parser.add_argument("--device", default="cpu", help="cpu, 0, 0,1, ...")
    parser.add_argument("--patience", type=int, default=20, help="early-stopping patience (epochs)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="print configuration and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = REPO_ROOT / data_path
    config = {
        "data": str(data_path),
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "name": args.name,
        "out": args.out,
        "device": args.device,
        "patience": args.patience,
        "workers": args.workers,
    }
    print("Training configuration:")
    print(json.dumps(config, indent=2))

    if args.dry_run:
        print("\n(dry run — no training started)")
        return 0

    if not data_path.exists():
        print(
            f"\nERROR: dataset config not found: {data_path}\n"
            "Prepare a dataset first — see docs/DATASETS.md and docs/MODEL_TRAINING.md.",
            file=sys.stderr,
        )
        return 2

    try:
        from ultralytics import YOLO
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nERROR: ultralytics/torch unavailable ({exc}).\n"
            "Install backend requirements first: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    print(f"\nStarting training at {time.strftime('%Y-%m-%d %H:%M:%S')} — this can take a long time on CPU...")
    model = YOLO(args.model)
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        project=str(REPO_ROOT / args.out),
        device=args.device,
        patience=args.patience,
        workers=args.workers,
        exist_ok=False,
    )

    save_dir = Path(str(getattr(results, "save_dir", "")) or REPO_ROOT / args.out / args.name)
    best = save_dir / "weights" / "best.pt"
    print("\nTraining finished.")
    print(f"  run directory : {save_dir}")
    print(f"  best weights  : {best if best.exists() else save_dir / 'weights' / 'last.pt'}")
    if best.exists():
        print("\nNext steps:")
        print("  $env:CUSTOM_WEIGHTS = 'runs/train/" + args.name + "/weights/best.pt'")
        print("  $env:INFERENCE_MODE = 'custom'")
        print("  then restart the backend and check /api/status")
    print("\nNOTE: metrics above come from THIS run only — validate before trusting them:")
    print("  python scripts/validate_model.py --weights <best.pt> --data <data.yaml>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
