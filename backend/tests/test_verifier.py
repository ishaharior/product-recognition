"""Verification decision rules — every status path must be explainable."""

from __future__ import annotations

import pytest

from src.verification.verifier import (
    ColourEvidence,
    ProductSpec,
    ProductVerifier,
    VerificationInput,
    VerificationThresholds,
    WeightEvidence,
)

TOL = 8.0


def make_product(**overrides) -> ProductSpec:
    defaults = dict(
        id="p1",
        sku="SKU-1",
        name="Test Product",
        expected_gross_weight_g=500.0,
        packaging_weight_g=40.0,
        weight_tolerance_pct=TOL,
        weight_spec_kind="gross",
        accepted_colours=[("red", "#e63946")],
    )
    defaults.update(overrides)
    return ProductSpec(**defaults)


def make_verifier() -> ProductVerifier:
    return ProductVerifier(
        VerificationThresholds(
            min_confidence=0.45,
            weight_tolerance_pct=TOL,
            colour_min_similarity=0.45,
            require_stable_weight=True,
        )
    )


def weight(grams, stable=True, source="real", empty=False) -> WeightEvidence:
    return WeightEvidence(grams=grams, stable=stable, source=source, empty=empty)


def colour(similarity=0.9, reliable=True, name="red", quality="good") -> ColourEvidence:
    return ColourEvidence(name=name, hex_value="#e63946", quality=quality,
                          reliable=reliable, similarity=similarity)


def test_no_detection():
    result = make_verifier().verify(VerificationInput(detected_label="", confidence=0.0))
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "No object" in result.explanation
    assert result.checks[0].passed is False


def test_verified_happy_path():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="demo cola can",
            confidence=0.93,
            product=make_product(),
            colour=colour(),
            weight=weight(500.0),
        )
    )
    assert result.status == "VERIFIED"
    assert result.explanation
    assert result.weight_delta_pct == pytest.approx(0.0)
    assert all(c.passed is not False for c in result.checks)
    assert any(c.name == "weight" and c.passed for c in result.checks)


def test_low_confidence_insufficient_evidence():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="demo cola can",
            confidence=0.31,
            product=make_product(),
            colour=colour(),
            weight=weight(500.0),
        )
    )
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "confidence" in result.explanation.lower()


def test_unknown_product():
    result = make_verifier().verify(
        VerificationInput(detected_label="mystery object", confidence=0.8, product=None)
    )
    assert result.status == "UNKNOWN_PRODUCT"
    assert "catalogue" in result.explanation.lower()
    assert any(c.name == "catalogue_match" and c.passed is False for c in result.checks)


def test_weight_mismatch_neutral_language():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),  # 500 g ±8%
            colour=colour(),
            weight=weight(400.0),  # -20%
        )
    )
    assert result.status == "WEIGHT_MISMATCH"
    assert "manual review recommended" in result.explanation.lower()
    banned = ("counterfeit", "fraud", "fake", "forgery")
    assert not any(word in result.explanation.lower() for word in banned)
    assert result.weight_delta_pct == pytest.approx(-20.0, abs=0.01)


def test_weight_within_tolerance_verified():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=weight(510.0),  # +2% within ±8%
        )
    )
    assert result.status == "VERIFIED"


def test_unstable_weight_blocks_verification():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=weight(500.0, stable=False),
        )
    )
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stabil" in result.explanation.lower()


def test_sensor_unavailable():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=None,
        )
    )
    assert result.status == "SENSOR_UNAVAILABLE"
    assert "sensor" in result.explanation.lower() or "reading" in result.explanation.lower()


def test_empty_scale_requires_placement():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=weight(0.0, empty=True),
        )
    )
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "empty" in result.explanation.lower()


def test_colour_mismatch():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),  # accepts red
            colour=colour(similarity=0.1, name="blue"),
            weight=weight(500.0),
        )
    )
    assert result.status == "COLOUR_MISMATCH"
    assert "manual review recommended" in result.explanation.lower()


def test_unreliable_colour_is_skipped_not_failed():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(similarity=None, reliable=False, quality="poor"),
            weight=weight(500.0),
        )
    )
    assert result.status == "VERIFIED"
    assert any(c.name == "colour" and c.passed is None for c in result.checks)
    assert any("colour" in w.lower() for w in result.warnings)


def test_simulated_weight_is_flagged():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=weight(500.0, source="simulated"),
            mode="demo",
        )
    )
    assert result.status == "VERIFIED"
    assert any("simulated" in w.lower() for w in result.warnings)


def test_net_spec_without_packaging_cannot_be_compared():
    product = make_product(
        expected_gross_weight_g=None,
        expected_net_weight_g=450.0,
        packaging_weight_g=None,
        weight_spec_kind="net",
    )
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=product,
            colour=colour(),
            weight=weight(495.0),
        )
    )
    # Without packaging weight a packaged measurement is not comparable.
    assert any(c.name == "weight" and c.passed is None for c in result.checks)
    assert any("packaging" in w.lower() for w in result.warnings)
    assert result.status == "VERIFIED"  # nothing else failed; weight just not checked


def test_net_spec_with_packaging_is_compared():
    product = make_product(
        expected_gross_weight_g=None,
        expected_net_weight_g=450.0,
        packaging_weight_g=50.0,
        weight_spec_kind="net",
    )
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=product,
            colour=colour(),
            weight=weight(600.0),  # way off 500 reconstructed gross
        )
    )
    assert result.status == "WEIGHT_MISMATCH"
    assert result.expected_weight_g == pytest.approx(500.0)


def test_gross_reconstructed_from_net_plus_packaging():
    product = make_product(
        expected_gross_weight_g=None,
        expected_net_weight_g=450.0,
        packaging_weight_g=50.0,
        weight_spec_kind="net",
    )
    expected, note = ProductVerifier.expected_weight_for_measurement(product)
    assert expected == pytest.approx(500.0)
    assert "reconstructed" in note


def test_gross_reconstructed_from_net_only_when_packaging_known():
    product = make_product(
        expected_gross_weight_g=None,
        expected_net_weight_g=450.0,
        packaging_weight_g=None,
        weight_spec_kind="gross",
    )
    expected, note = ProductVerifier.expected_weight_for_measurement(product)
    assert expected is None
    assert "no gross weight" in note


def test_every_result_carries_explanation_and_checks():
    verifier = make_verifier()
    inputs = [
        VerificationInput(detected_label="x", confidence=0.9, product=make_product(),
                          colour=colour(), weight=weight(500.0)),
        VerificationInput(detected_label="x", confidence=0.1),
        VerificationInput(detected_label="x", confidence=0.9, product=None),
        VerificationInput(detected_label="x", confidence=0.9, product=make_product(),
                          colour=None, weight=None),
    ]
    for data in inputs:
        result = verifier.verify(data)
        assert result.explanation
        assert result.to_dict()["status"] in {
            "VERIFIED", "REVIEW_REQUIRED", "UNKNOWN_PRODUCT", "WEIGHT_MISMATCH",
            "COLOUR_MISMATCH", "SENSOR_UNAVAILABLE", "INSUFFICIENT_EVIDENCE",
        }


def test_mismatch_priority_weight_over_colour():
    result = make_verifier().verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(similarity=0.1),
            weight=weight(100.0),
        )
    )
    assert result.status == "WEIGHT_MISMATCH"  # weight mismatch outranks colour


def test_vision_only_mode_skips_weight_when_excluded():
    """With require_weight=False (experiment baseline) missing weight is not a failure."""
    verifier = ProductVerifier(
        VerificationThresholds(min_confidence=0.45, require_weight=False)
    )
    result = verifier.verify(
        VerificationInput(
            detected_label="x",
            confidence=0.9,
            product=make_product(),
            colour=colour(),
            weight=None,
        )
    )
    assert result.status == "VERIFIED"
    weight_checks = [c for c in result.checks if c.name == "weight"]
    assert weight_checks and weight_checks[0].passed is None
    assert "vision-only" in weight_checks[0].detail
