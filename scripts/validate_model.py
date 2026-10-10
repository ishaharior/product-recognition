"""Validate a trained YOLO checkpoint against a labelled split (opt-in).

Example:

    python scripts/validate_model.py --weights runs/train/station-v1/weights/best.pt \
        --data data/dataset_config.yaml --split val

Reports precision / recall / mAP50-95 computed by Ultralytics on the chosen
split. These numbers describe THIS run on THIS split only — they are not a
general claim about production accuracy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", required=True, help="path to best.pt / last.pt")
    parser.add_argument("--data", required=True, help="dataset.yaml with a val/test split")
    parser.add_argument("--split", choices=["train", "val", "test"], default="val")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", help="optional path to write metrics JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    weights = Path(args.weights)
    if not weights.is_absolute():
        weights = REPO_ROOT / weights
    data = Path(args.data)
    if not data.is_absolute():
        data = REPO_ROOT / data

    for label, path in (("--weights", weights), ("--data", data)):
        if not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            return 2

    try:
        from ultralytics import YOLO
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: ultralytics unavailable ({exc})", file=sys.stderr)
        return 2

    print(f"Validating {weights.name} on split '{args.split}' ({data}) ...")
    model = YOLO(str(weights))
    metrics = model.val(
        data=str(data),
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        verbose=True,
    )

    box = getattr(metrics, "box", None)
    summary = {
        "weights": str(weights),
        "data": str(data),
        "split": args.split,
        "precision": float(getattr(box, "mp", 0.0) or 0.0),
        "recall": float(getattr(box, "mr", 0.0) or 0.0),
        "map50": float(getattr(box, "map50", 0.0) or 0.0),
        "map50_95": float(getattr(box, "map", 0.0) or 0.0),
        "note": "Metrics computed for this split/run only.",
    }
    print("\nSummary:")
    print(json.dumps(summary, indent=2))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
