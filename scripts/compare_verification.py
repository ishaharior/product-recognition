"""Comparison experiment: vision-only vs multimodal verification.

Evaluates the *verification layer* (not the detector itself) on a labelled set
of observations and reports accuracy, precision, recall and false-acceptance
rate (FAR) for two configurations:

  1. vision-only  — label confidence + catalogue match only (no colour, no weight)
  2. multimodal   — label confidence + catalogue match + colour + weight

Labelled data
-------------
Provide your own CSV (see --write-template) with one row per labelled
observation, or generate a clearly-marked SIMULATED sample:

    python scripts/compare_verification.py --generate-sample data/experiment_sample.csv
    python scripts/compare_verification.py --input data/experiment_sample.csv

The simulated sample exists to demonstrate the harness end-to-end; metrics
obtained from it are NOT experimental findings about real products and the
output repeats that warning. To produce real findings, export real labelled
scans (e.g. from scan history + ground truth) into the same CSV format.

CSV columns:
    sku, detected_label, confidence, colour_name, colour_hex, colour_similarity,
    colour_quality, weight_g, weight_stable, weight_source, ground_truth
where ground_truth is `accept` or `reject`.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.catalogue import DEMO_PRODUCTS  # noqa: E402
from src.verification.verifier import (  # noqa: E402
    ColourEvidence,
    ProductSpec,
    ProductVerifier,
    VerificationInput,
    VerificationThresholds,
    WeightEvidence,
)

TEMPLATE_COLUMNS = [
    "sku", "detected_label", "confidence", "colour_name", "colour_hex",
    "colour_similarity", "colour_quality", "weight_g", "weight_stable",
    "weight_source", "ground_truth",
]


def product_specs() -> dict[str, ProductSpec]:
    specs: dict[str, ProductSpec] = {}
    for row in DEMO_PRODUCTS:
        specs[row["sku"]] = ProductSpec(
            id=row["sku"],
            sku=row["sku"],
            name=row["name"],
            expected_gross_weight_g=row["expected_gross_weight_g"],
            packaging_weight_g=row.get("packaging_weight_g"),
            weight_tolerance_pct=row.get("weight_tolerance_pct", 10.0),
            weight_spec_kind=row.get("weight_spec_kind", "gross"),  # type: ignore[arg-type]
            accepted_colours=list(row.get("colours", [])),
            model_class_names=[row.get("model_class_names", "")],
        )
    return specs


def write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "sku": "DEMO-001",
                "detected_label": "demo cola can",
                "confidence": "0.91",
                "colour_name": "red",
                "colour_hex": "#e63946",
                "colour_similarity": "0.88",
                "colour_quality": "good",
                "weight_g": "355.4",
                "weight_stable": "1",
                "weight_source": "real",
                "ground_truth": "accept",
            }
        )


def generate_sample(path: Path, seed: int = 1234, rows: int = 240) -> None:
    """Deterministic SYNTHETIC labelled sample (explicitly not real data)."""
    rng = random.Random(seed)
    specs = product_specs()
    skus = list(specs.keys())
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        for i in range(rows):
            sku = skus[i % len(skus)]
            spec = specs[sku]
            expected = spec.expected_gross_weight_g or 0.0
            colour = spec.accepted_colours[0]
            colour_similarity = round(rng.uniform(0.6, 0.95), 3)
            confidence = round(rng.uniform(0.55, 0.97), 3)
            weight = round(expected * rng.uniform(0.97, 1.03), 1)
            ground = "accept"

            kind = i % 8
            if kind == 0:
                # wrong weight — only a sensor can catch this
                weight = round(expected * rng.uniform(0.68, 0.85), 1)
                ground = "reject"
            elif kind == 1:
                # wrong colour — vision can catch this
                colour = ("blue", "#457b9d") if colour[0] != "blue" else ("green", "#2a9d8f")
                colour_similarity = round(rng.uniform(0.05, 0.3), 3)
                ground = "reject"
            elif kind == 2:
                # weak detection — both configurations should reject
                confidence = round(rng.uniform(0.1, 0.4), 3)
                ground = "reject"

            writer.writerow(
                {
                    "sku": sku,
                    "detected_label": spec.model_class_names[0] or spec.name,
                    "confidence": confidence,
                    "colour_name": colour[0],
                    "colour_hex": colour[1],
                    "colour_similarity": colour_similarity,
                    "colour_quality": "good",
                    "weight_g": weight,
                    "weight_stable": 1,
                    "weight_source": "simulated",
                    "ground_truth": ground,
                }
            )


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in TEMPLATE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"ERROR: CSV missing columns: {', '.join(missing)}")
        return list(reader)


def _evaluate(rows: list[dict], use_colour: bool, use_weight: bool) -> dict:
    verifier = ProductVerifier(
        VerificationThresholds(
            min_confidence=0.45,
            weight_tolerance_pct=10.0,
            colour_min_similarity=0.45,
            # Vision-only must not be punished for having no weight evidence:
            # it is judged on identity + confidence (+ colour when included).
            require_weight=use_weight,
        )
    )
    specs = product_specs()

    tp = fp = tn = fn = 0
    per_row: list[tuple[str, str]] = []
    for row in rows:
        spec = specs.get(row["sku"])
        colour = None
        if use_colour:
            colour = ColourEvidence(
                name=row["colour_name"],
                hex_value=row["colour_hex"],
                quality=row.get("colour_quality", "good"),
                reliable=row.get("colour_quality", "good") in {"good", "fair"},
                similarity=float(row["colour_similarity"]) if row["colour_similarity"] else None,
            )
        weight = None
        if use_weight and row.get("weight_g"):
            src_raw = (row.get("weight_source") or "none").strip().lower()
            weight = WeightEvidence(
                grams=float(row["weight_g"]),
                stable=row.get("weight_stable", "1") in {"1", "true", "True"},
                source=src_raw if src_raw in {"real", "simulated"} else "none",  # type: ignore[arg-type]
            )
        result = verifier.verify(
            VerificationInput(
                detected_label=row["detected_label"],
                confidence=float(row["confidence"]),
                product=spec,
                colour=colour,
                weight=weight,
                mode="experiment",
            )
        )
        predicted_accept = result.status == "VERIFIED"
        actual_accept = row["ground_truth"].strip().lower() == "accept"
        per_row.append((result.status, row["ground_truth"]))
        if predicted_accept and actual_accept:
            tp += 1
        elif predicted_accept and not actual_accept:
            fp += 1
        elif not predicted_accept and actual_accept:
            fn += 1
        else:
            tn += 1

    total = len(rows) or 1
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    far = fp / (fp + tn) if (fp + tn) else 0.0  # rejection opportunity false-accept rate
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return {
        "rows": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_acceptance_rate": round(far, 4),
        "false_rejection_rate": round(fnr, 4),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="labelled CSV (see --write-template)")
    parser.add_argument("--generate-sample", metavar="PATH", help="write a SIMULATED labelled CSV and continue")
    parser.add_argument("--write-template", metavar="PATH", help="write an empty CSV template and exit")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--rows", type=int, default=240)
    parser.add_argument("--out", help="optional path for metrics JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_template:
        write_template(Path(args.write_template))
        print(f"Template written to {args.write_template}")
        return 0

    simulated = False
    if args.generate_sample:
        generate_sample(Path(args.generate_sample), seed=args.seed, rows=args.rows)
        print(f"SIMULATED sample written to {args.generate_sample}")
        args.input = args.generate_sample
        simulated = True

    if not args.input:
        build_parser().print_help()
        return 2

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: input not found: {path}", file=sys.stderr)
        return 2

    rows = load_rows(path)
    if not rows:
        print("ERROR: input CSV has no data rows", file=sys.stderr)
        return 2
    if any(r.get("weight_source") == "simulated" for r in rows):
        simulated = True

    vision_only = _evaluate(rows, use_colour=False, use_weight=False)
    multimodal = _evaluate(rows, use_colour=True, use_weight=True)

    report = {
        "input": str(path),
        "rows": len(rows),
        "simulated_data": simulated,
        "vision_only": vision_only,
        "multimodal": multimodal,
        "delta_accuracy": round(multimodal["accuracy"] - vision_only["accuracy"], 4),
        "delta_far": round(multimodal["false_acceptance_rate"] - vision_only["false_acceptance_rate"], 4),
        "warning": (
            "SIMULATED INPUT — these metrics demonstrate the harness only and are NOT "
            "experimental findings about real products."
            if simulated
            else "Metrics computed from the supplied labelled CSV."
        ),
    }

    print()
    print("=" * 72)
    print("Vision-only vs multimodal verification comparison")
    print("=" * 72)
    if simulated:
        print("!! SIMULATED INPUT — NOT a real experimental result. !!")
    for label, block in (("vision-only", vision_only), ("multimodal", multimodal)):
        print(f"\n{label}:")
        for key in (
            "accuracy", "precision", "recall",
            "false_acceptance_rate", "false_rejection_rate",
        ):
            print(f"  {key:24s} {block[key]:.4f}")
        print(f"  {'confusion (tp/fp/tn/fn)':24s} {block['tp']}/{block['fp']}/{block['tn']}/{block['fn']}")
    print(f"\ndelta accuracy (multimodal - vision-only): {report['delta_accuracy']:+.4f}")
    print(f"delta FAR       (multimodal - vision-only): {report['delta_far']:+.4f}")
    print(f"\n{report['warning']}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
