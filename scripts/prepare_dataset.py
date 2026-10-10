"""Dataset preparation CLI (opt-in — never downloads anything by itself).

Usage examples (run from the repository root):

    python scripts/prepare_dataset.py inspect data/datasets/my_raw_data
    python scripts/prepare_dataset.py convert data/datasets/my_raw_data data/datasets/converted --format voc
    python scripts/prepare_dataset.py split data/datasets/converted data/datasets/ship --seed 42
    python scripts/prepare_dataset.py config data/datasets/ship data/dataset_config.yaml --names cola juice
    python scripts/prepare_dataset.py merge data/datasets/combined --inputs data/datasets/a data/datasets/b

Supported annotation formats: YOLO (txt), PASCAL VOC (xml), COCO (json).
See docs/DATASETS.md for download instructions and licences.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.datasets.prepare import (  # noqa: E402
    DatasetError,
    convert_to_yolo,
    deterministic_split,
    detect_format,
    inspect_dataset,
    merge_yolo_datasets,
    write_data_yaml,
)


def cmd_inspect(args: argparse.Namespace) -> int:
    report = inspect_dataset(Path(args.dataset))
    print(json.dumps(report.to_dict(), indent=2))
    if report.class_counts:
        try:
            import pandas as pd

            table = pd.DataFrame(
                [{"class": k, "count": v} for k, v in report.class_counts.items()]
            )
            print("\nClass counts:")
            print(table.to_string(index=False))
        except ImportError:  # pragma: no cover
            for k, v in report.class_counts.items():
                print(f"  {k}: {v}")
    if report.detected_format == "unsupported":
        print("\nUNSUPPORTED dataset format.", file=sys.stderr)
        return 2
    if not report.ok:
        print("\nDataset has problems (see lists above).", file=sys.stderr)
        return 1
    print("\nDataset looks consistent.")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    src, dst = Path(args.src), Path(args.dst)
    fmt = None if args.format == "auto" else args.format
    names = None
    if args.names:
        names = [n.strip() for n in args.names.split(",") if n.strip()]
    summary = convert_to_yolo(src, dst, fmt=fmt, class_names=names)
    print(json.dumps(summary, indent=2))
    print(f"\nConverted dataset written to {dst}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    ratios = tuple(float(r) for r in args.ratios)
    if len(ratios) != 3:
        print("--ratios takes exactly three values (train val test)", file=sys.stderr)
        return 2
    summary = deterministic_split(
        Path(args.dataset), Path(args.out), ratios=ratios, seed=args.seed  # type: ignore[arg-type]
    )
    print(json.dumps(summary, indent=2))
    print("\nLeakage-free split written (each image appears in exactly one subset).")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    root = Path(args.dataset)
    names = [n.strip() for n in args.names.split(",") if n.strip()] if args.names else []
    if not names:
        classes_file = root / "classes.txt"
        if classes_file.exists():
            names = [line.strip() for line in classes_file.read_text().splitlines() if line.strip()]
    if not names:
        print("No class names: pass --names or provide classes.txt", file=sys.stderr)
        return 2
    out = write_data_yaml(
        Path(args.out),
        train_dir=Path("train/images"),
        val_dir=Path("val/images"),
        test_dir=Path("test/images") if (root / "test").exists() else None,
        class_names=names,
        path=root.resolve(),
    )
    print(f"Dataset config written to {out}")
    print(out.read_text(encoding="utf-8"))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    summary = merge_yolo_datasets(
        [Path(p) for p in args.inputs], Path(args.out)
    )
    print(json.dumps(summary, indent=2))
    print(f"\nMerged dataset written to {args.out}")
    print(summary["next_step"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="inspect images/labels and report problems")
    p.add_argument("dataset")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("convert", help="convert VOC/COCO/YOLO to YOLO layout")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--format", choices=["auto", "yolo", "voc", "coco"], default="auto")
    p.add_argument("--names", help="comma-separated class names (order defines class ids)")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("split", help="deterministic leakage-free train/val/test split")
    p.add_argument("dataset")
    p.add_argument("out")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--ratios", nargs=3, default=["0.8", "0.1", "0.1"], metavar=("TRAIN", "VAL", "TEST"))
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("config", help="write an Ultralytics dataset.yaml")
    p.add_argument("dataset")
    p.add_argument("out")
    p.add_argument("--names", help="comma-separated class names (default: classes.txt)")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser(
        "merge",
        help="merge multiple YOLO datasets (class remap + cross-source dedupe)",
    )
    p.add_argument("out", help="output directory (must not exist or be empty)")
    p.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        metavar="DATASET",
        help="two or more prepared YOLO dataset roots (classes.txt or dataset.yaml each)",
    )
    p.set_defaults(func=cmd_merge)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
