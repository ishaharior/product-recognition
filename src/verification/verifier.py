"""Multimodal product verification.

Combines vision recognition (label + confidence), colour estimation, physical
weight and catalogue specifications into one explainable decision.

Design rules
------------
* Every decision carries a human-readable explanation and per-check details.
* Weight is only compared against a specification of the *same kind*
  (gross vs net). A gross (packaged) measurement is never silently compared
  with a net-weight specification.
* Unstable or missing sensor readings never count as evidence.
* Language stays neutral: mismatches trigger "manual review recommended",
  never accusations of counterfeiting or fraud.
* Thresholds are configurable and injected, not hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

VerificationStatus = Literal[
    "VERIFIED",
    "REVIEW_REQUIRED",
    "UNKNOWN_PRODUCT",
    "WEIGHT_MISMATCH",
    "COLOUR_MISMATCH",
    "SENSOR_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE",
]

# Status precedence when multiple issues apply (lower = reported first).
_STATUS_RANK = {
    "WEIGHT_MISMATCH": 0,
    "COLOUR_MISMATCH": 1,
    "UNKNOWN_PRODUCT": 2,
    "SENSOR_UNAVAILABLE": 3,
    "INSUFFICIENT_EVIDENCE": 4,
    "REVIEW_REQUIRED": 5,
    "VERIFIED": 6,
}


@dataclass
class ColourEvidence:
    """Colour evidence extracted by the vision pipeline."""

    name: str = "unknown"
    hex_value: str = ""
    quality: str = "unknown"
    reliable: bool = False
    similarity: float | None = None  # 0..1 against accepted variant, if computed
    warnings: list[str] = field(default_factory=list)


@dataclass
class WeightEvidence:
    grams: float | None = None
    stable: bool = False
    source: Literal["real", "simulated", "none"] = "none"
    empty: bool = False  # platform reads empty (nothing placed on the scale)


@dataclass
class ProductSpec:
    """Catalogue information needed for verification (ORM-free)."""

    id: str
    sku: str
    name: str
    expected_gross_weight_g: float | None = None
    expected_net_weight_g: float | None = None
    packaging_weight_g: float | None = None
    weight_tolerance_pct: float = 10.0
    weight_spec_kind: Literal["gross", "net"] = "gross"
    accepted_colours: list[tuple[str, str]] = field(default_factory=list)  # (name, hex)
    model_class_names: list[str] = field(default_factory=list)


@dataclass
class VerificationThresholds:
    min_confidence: float = 0.45
    weight_tolerance_pct: float = 10.0
    colour_min_similarity: float = 0.45
    require_stable_weight: bool = True
    require_weight: bool = True  # False = vision-only evaluation (weight not checked)
    colour_required: bool = False  # colour mismatch only blocks when True? -> kept False


@dataclass
class VerificationInput:
    detected_label: str = ""
    confidence: float = 0.0
    product: ProductSpec | None = None
    colour: ColourEvidence | None = None
    weight: WeightEvidence | None = None
    mode: str = "baseline"
    source: str = "live"


@dataclass
class Check:
    name: str
    passed: bool | None  # None = not evaluated
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class VerificationResult:
    status: VerificationStatus
    explanation: str
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    weight_delta_pct: float | None = None
    colour_similarity: float | None = None
    expected_weight_g: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "explanation": self.explanation,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": list(self.warnings),
            "weight_delta_pct": None if self.weight_delta_pct is None else round(self.weight_delta_pct, 2),
            "colour_similarity": None
            if self.colour_similarity is None
            else round(self.colour_similarity, 3),
            "expected_weight_g": self.expected_weight_g,
        }


class ProductVerifier:
    """Rule-based fusion of vision, colour and weight evidence."""

    def __init__(self, thresholds: VerificationThresholds | None = None) -> None:
        self.thresholds = thresholds or VerificationThresholds()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def expected_weight_for_measurement(
        spec: ProductSpec, measurement_kind: Literal["gross"] = "gross"
    ) -> tuple[float | None, str]:
        """Expected weight in grams for a *gross* measurement, or (None, reason)."""
        if spec.weight_spec_kind == "gross":
            if spec.expected_gross_weight_g is not None:
                return spec.expected_gross_weight_g, "gross specification"
            if spec.expected_net_weight_g is not None and spec.packaging_weight_g is not None:
                return (
                    spec.expected_net_weight_g + spec.packaging_weight_g,
                    "net + packaging (gross reconstructed)",
                )
            return None, "no gross weight specification available"
        # net specification
        if spec.expected_net_weight_g is None:
            return None, "no net weight specification available"
        if spec.packaging_weight_g is None:
            # A gross measurement includes packaging; without a packaging weight
            # we cannot fairly compare it against a net specification.
            return None, (
                "net specification but packaging weight unknown — a packaged "
                "measurement cannot be compared fairly"
            )
        return (
            spec.expected_net_weight_g + spec.packaging_weight_g,
            "net + packaging (gross reconstructed)",
        )

    def weight_delta_pct(self, measured_g: float, expected_g: float) -> float:
        if expected_g == 0:
            return 0.0
        return (measured_g - expected_g) / expected_g * 100.0

    # ------------------------------------------------------------------ main
    def verify(self, data: VerificationInput) -> VerificationResult:
        t = self.thresholds
        checks: list[Check] = []
        warnings: list[str] = []
        status_pool: list[VerificationStatus] = []
        explanations: list[str] = []
        weight_delta: float | None = None
        colour_sim: float | None = None
        expected_g: float | None = None

        # 1) recognition ------------------------------------------------------
        label = (data.detected_label or "").strip()
        if not label:
            checks.append(Check("recognition", False, "No object detected in the frame."))
            return VerificationResult(
                status="INSUFFICIENT_EVIDENCE",
                explanation="No object was detected — nothing to verify.",
                checks=checks,
                warnings=warnings,
            )

        if data.confidence < t.min_confidence:
            checks.append(
                Check(
                    "recognition",
                    False,
                    f"Confidence {data.confidence:.2f} below threshold {t.min_confidence:.2f}.",
                )
            )
            status_pool.append("INSUFFICIENT_EVIDENCE")
            explanations.append(
                f"Detection confidence ({data.confidence:.2f}) is below the required "
                f"threshold ({t.min_confidence:.2f}); evidence is insufficient."
            )
        else:
            checks.append(
                Check("recognition", True, f"Confidence {data.confidence:.2f} meets threshold.")
            )

        # 2) catalogue match --------------------------------------------------
        product = data.product
        if product is None:
            checks.append(
                Check(
                    "catalogue_match",
                    False,
                    f"Detected label '{label}' has no catalogue entry.",
                )
            )
            status_pool.append("UNKNOWN_PRODUCT")
            explanations.append(
                f"Detected '{label}' could not be matched to a product in the catalogue — "
                "identity unknown for this station."
            )
        else:
            checks.append(
                Check(
                    "catalogue_match",
                    True,
                    f"Matched catalogue product {product.name} ({product.sku}).",
                )
            )

        # 3) weight -----------------------------------------------------------
        weight = data.weight
        if product is not None:
            expected_g, expected_note = self.expected_weight_for_measurement(product, "gross")
            if expected_g is None:
                warnings.append(f"Weight not checked: {expected_note}.")
                checks.append(Check("weight", None, f"Not checked — {expected_note}."))
            elif weight is None or weight.grams is None or weight.source == "none":
                if not t.require_weight:
                    checks.append(
                        Check("weight", None, "Not checked — weight evidence excluded (vision-only).")
                    )
                else:
                    checks.append(
                        Check("weight", None, "No weight reading available (sensor unavailable).")
                    )
                    status_pool.append("SENSOR_UNAVAILABLE")
                    explanations.append(
                        "Weight could not be verified because no sensor reading is available. "
                        "Vision evidence alone is not sufficient for full verification."
                    )
            elif weight.empty:
                checks.append(
                    Check("weight", None, "Scale reads empty — no load on the platform.")
                )
                status_pool.append("INSUFFICIENT_EVIDENCE")
                explanations.append(
                    "The scale currently reads empty — place the product on the platform "
                    "to enable weight verification."
                )
            elif t.require_stable_weight and not weight.stable:
                checks.append(
                    Check("weight", None, "Weight reading present but not stable yet.")
                )
                status_pool.append("INSUFFICIENT_EVIDENCE")
                explanations.append(
                    "A weight reading was received but it has not stabilised — "
                    "stable measurements are required before weight verification."
                )
            else:
                expected_g = float(expected_g)
                weight_delta = self.weight_delta_pct(float(weight.grams), expected_g)
                tolerance = product.weight_tolerance_pct or t.weight_tolerance_pct
                inside = abs(weight_delta) <= tolerance
                detail = (
                    f"Measured {weight.grams:.1f} g vs expected {expected_g:.1f} g "
                    f"({expected_note}), delta {weight_delta:+.1f}%, tolerance ±{tolerance:.1f}%."
                )
                if weight.source == "simulated":
                    detail += " [SIMULATED reading]"
                    warnings.append("Weight source is simulated, not a real sensor measurement.")
                checks.append(Check("weight", inside, detail))
                if not inside:
                    status_pool.append("WEIGHT_MISMATCH")
                    explanations.append(
                        f"Mismatch detected: measured weight differs from the expected "
                        f"specification by {weight_delta:+.1f}% (allowed ±{tolerance:.1f}%). "
                        "Manual review recommended."
                    )
                else:
                    explanations.append(
                        f"Measured weight is within the ±{tolerance:.1f}% tolerance of the "
                        "expected specification."
                    )
        else:
            checks.append(Check("weight", None, "Not checked — no catalogue match."))

        # 4) colour -----------------------------------------------------------
        colour = data.colour
        if product is not None and colour is not None:
            accepted = product.accepted_colours
            if not accepted:
                checks.append(
                    Check("colour", None, "Not checked — no reference colours for this product.")
                )
            elif colour.reliable and colour.similarity is not None:
                colour_sim = colour.similarity
                inside = colour_sim >= t.colour_min_similarity
                checks.append(
                    Check(
                        "colour",
                        inside,
                        f"Estimated '{colour.name}' vs accepted "
                        f"{[a[0] for a in accepted]} — similarity {colour_sim:.2f} "
                        f"(threshold {t.colour_min_similarity:.2f}, quality={colour.quality}).",
                    )
                )
                if not inside:
                    status_pool.append("COLOUR_MISMATCH")
                    explanations.append(
                        "Colour mismatch detected: the estimated product colour is not "
                        "compatible with the catalogue reference under current lighting. "
                        "Manual review recommended."
                    )
                else:
                    explanations.append("Estimated colour is compatible with the catalogue reference.")
            else:
                checks.append(
                    Check(
                        "colour",
                        None,
                        f"Not checked — colour quality is '{colour.quality}' (unreliable).",
                    )
                )
                warnings.append(
                    "Colour was not used for verification (poor lighting or small region)."
                )
                if colour.warnings:
                    warnings.extend(colour.warnings)
        else:
            checks.append(Check("colour", None, "Not checked — no colour evidence."))

        # 5) confidence-based review ------------------------------------------
        if data.confidence >= t.min_confidence and data.confidence < max(
            t.min_confidence + 0.15, 0.60
        ):
            if not status_pool:
                status_pool.append("REVIEW_REQUIRED")
                explanations.append(
                    f"Detection confidence ({data.confidence:.2f}) is acceptable but not "
                    "strong — manual review recommended."
                )

        # ------------------------------------------------------------------ decide
        if not status_pool:
            status: VerificationStatus = "VERIFIED"
            explanations.insert(
                0,
                "All checks passed: identity, weight (where available) and colour "
                "are consistent with the catalogue specification.",
            )
        else:
            status = min(status_pool, key=lambda s: _STATUS_RANK[s])

        # VERIFIED requires all evaluated checks to have passed
        if status == "VERIFIED" and any(c.passed is False for c in checks):
            status = "REVIEW_REQUIRED"

        explanation = " ".join(explanations) if explanations else "No explanation available."
        if data.mode == "demo" or (weight and weight.source == "simulated"):
            warnings.append("Simulated data involved — result is for demonstration only.")

        return VerificationResult(
            status=status,
            explanation=explanation,
            checks=checks,
            warnings=_dedupe(warnings),
            weight_delta_pct=weight_delta,
            colour_similarity=colour_sim,
            expected_weight_g=expected_g,
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)
