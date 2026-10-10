"""Colour-analysis logic on synthetic images (NOT real camera validation)."""

from __future__ import annotations

import numpy as np

from src.vision.color_analyzer import (
    analyse_similarity_to_accepted,
    analyze_colour,
    colour_similarity,
    crop_region,
    delta_e76,
    name_for_hsv_pixel,
    rgb_hex_to_lab,
)


def solid_image(bgr: tuple[int, int, int], size: tuple[int, int] = (300, 300)) -> np.ndarray:
    h, w = size
    return np.full((h, w, 3), bgr, dtype=np.uint8)


def test_crop_region_clips_to_bounds():
    img = solid_image((0, 0, 255))
    crop = crop_region(img, (-50, -50, 500, 500))
    assert crop.shape[:2] == (300, 300)
    empty = crop_region(img, (10, 10, 10, 40))
    assert empty.size == 0


def test_dominant_red():
    img = solid_image((0, 0, 230))  # red in BGR
    result = analyze_colour(img, (20, 20, 280, 280))
    assert result.name == "red"
    assert result.hex_value.startswith("#")
    assert sum(result.distribution.values()) >= 0.99
    assert result.reliable is True
    assert result.mean_lab[1] > 40  # a* positive for red


def test_dominant_blue():
    img = solid_image((220, 60, 30))  # blue-ish BGR
    result = analyze_colour(img, (20, 20, 280, 280))
    assert result.name == "blue"


def test_neutrals():
    assert analyze_colour(solid_image((245, 245, 245)), (10, 10, 290, 290)).name == "white"
    assert analyze_colour(solid_image((20, 20, 20)), (10, 10, 290, 290)).name == "black"
    assert analyze_colour(solid_image((128, 128, 128)), (10, 10, 290, 290)).name == "grey"


def test_empty_region_reports_poor_quality():
    img = solid_image((0, 255, 0))
    result = analyze_colour(img, (100, 100, 100, 100))
    assert result.quality == "poor"
    assert result.reliable is False
    assert result.warnings


def test_small_region_warning():
    img = solid_image((0, 0, 230), (400, 400))
    result = analyze_colour(img, (10, 10, 30, 30))  # 20x20 = 400 px, below default 400? equal
    result_small = analyze_colour(img, (10, 10, 24, 24), min_pixels=500)
    assert any("small" in w.lower() for w in result_small.warnings)
    assert result_small.quality != "good"


def test_low_light_warning():
    img = solid_image((30, 20, 25), (300, 300))  # very dark reddish
    result = analyze_colour(img, (20, 20, 280, 280))
    assert any("low lighting" in w.lower() for w in result.warnings)
    assert result.reliable is False


def test_delta_e_and_similarity():
    lab_red = rgb_hex_to_lab("#e63946")
    lab_red2 = rgb_hex_to_lab("#e13b49")
    lab_blue = rgb_hex_to_lab("#457b9d")
    assert delta_e76(lab_red, lab_red) == 0.0
    assert delta_e76(lab_red, lab_red2) < 15
    assert delta_e76(lab_red, lab_blue) > 30


def test_similarity_to_accepted_combines_name_and_hex():
    img = solid_image((0, 0, 230))
    result = analyze_colour(img, (20, 20, 280, 280))
    assert analyse_similarity_to_accepted(result, [("red", "#e63946")]) > 0.6
    assert analyse_similarity_to_accepted(result, [("blue", "#457b9d")]) < 0.45
    assert analyse_similarity_to_accepted(result, []) == 0.0


def test_colour_similarity_zero_for_unknown():
    from src.vision.color_analyzer import ColourResult

    unknown = ColourResult(name="unknown")
    assert colour_similarity(unknown, "#ff0000") == 0.0


def test_pixel_naming_rules():
    assert name_for_hsv_pixel(h=0, s=200, v=200) == "red"
    assert name_for_hsv_pixel(h=174, s=200, v=200) == "red"  # wrap-around red
    assert name_for_hsv_pixel(h=110, s=200, v=200) == "blue"
    assert name_for_hsv_pixel(h=30, s=10, v=250) == "white"  # near-white, desaturated
    assert name_for_hsv_pixel(h=30, s=10, v=200) == "grey"  # desaturated mid-high value
    assert name_for_hsv_pixel(h=30, s=200, v=30) == "black"
