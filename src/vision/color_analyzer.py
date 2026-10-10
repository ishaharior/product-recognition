"""Camera-based colour estimation for a detected product region.

IMPORTANT: everything here is an *estimate* from a compressed camera frame
under uncontrolled lighting. It is not laboratory-grade colour measurement.
Results therefore carry a quality indicator and explicit warnings when the
region is too small, too dark/bright, or has too little chroma to name
reliably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import cv2
import numpy as np

# Named palette: (hue_lo, hue_hi, sat_lo, val_lo, val_hi, name, hex)
# HSV hue is 0..179 in OpenCV. Ranges may wrap near red (handled below).
_PALETTE: list[tuple[int, int, int, int, int, str, str]] = [
    #  h_lo h_hi  s_lo  v_lo v_hi  name        hex
    (0, 10, 90, 60, 255, "red", "#e63946"),
    (10, 25, 90, 60, 255, "orange", "#f77f00"),
    (25, 38, 90, 60, 255, "yellow", "#fcbf49"),
    (38, 85, 70, 50, 255, "green", "#2a9d8f"),
    (85, 100, 70, 50, 255, "cyan", "#43d3d9"),
    (100, 130, 70, 40, 255, "blue", "#457b9d"),
    (130, 150, 60, 40, 255, "purple", "#7b5ea7"),
    (150, 170, 55, 45, 240, "pink", "#e891b0"),
    (170, 179, 90, 60, 255, "red", "#e63946"),
]

_NEUTRAL_MIN_S = 60  # below this saturation we treat colour as neutral


@dataclass
class ColourResult:
    """Structured colour analysis of one region."""

    name: str = "unknown"
    hex_value: str = ""
    distribution: dict[str, float] = field(default_factory=dict)
    quality: str = "unknown"  # good | fair | poor | unknown
    warnings: list[str] = field(default_factory=list)
    pixel_count: int = 0
    mean_saturation: float = 0.0
    mean_value: float = 0.0
    mean_lab: tuple[float, float, float] = (0.0, 0.0, 0.0)
    reliable: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hex_value": self.hex_value,
            "distribution": {k: round(v, 4) for k, v in self.distribution.items()},
            "quality": self.quality,
            "warnings": list(self.warnings),
            "pixel_count": self.pixel_count,
            "mean_saturation": round(self.mean_saturation, 2),
            "mean_value": round(self.mean_value, 2),
            "mean_lab": [round(v, 2) for v in self.mean_lab],
            "reliable": self.reliable,
        }


def crop_region(image_bgr: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Clip and crop ``(x1, y1, x2, y2)`` to the image bounds."""
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = box
    x1, y1 = max(0, min(int(x1), w)), max(0, min(int(y1), h))
    x2, y2 = max(0, min(int(x2), w)), max(0, min(int(y2), h))
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=image_bgr.dtype)
    return image_bgr[y1:y2, x1:x2]


def _border_mask(region: np.ndarray) -> np.ndarray:
    """Conservative background exclusion: drop pixels outside the 10% border
    ring *only when* the ring is statistically different from the interior —
    a cheap heuristic that works when the product is centred on the frame."""
    h, w = region.shape[:2]
    if h < 10 or w < 10:
        return np.ones((h, w), dtype=bool)
    ring = max(1, min(h, w) // 10)
    inner = region[ring : h - ring, ring : w - ring]
    if inner.size == 0:
        return np.ones((h, w), dtype=bool)
    inner_mean = inner.reshape(-1, 3).mean(axis=0)
    ring_px = np.concatenate(
        [
            region[:ring, :].reshape(-1, 3),
            region[h - ring :, :].reshape(-1, 3),
            region[:, :ring].reshape(-1, 3),
            region[:, w - ring :].reshape(-1, 3),
        ]
    )
    dist = np.linalg.norm(ring_px.astype(np.float32) - inner_mean.astype(np.float32), axis=1)
    if float(dist.mean()) < 35.0:
        return np.ones((h, w), dtype=bool)  # border looks like the product: keep all
    mask = np.zeros((h, w), dtype=bool)
    mask[ring : h - ring, ring : w - ring] = True
    return mask


def name_for_hsv_pixel(h: int, s: int, v: int, low_s: int = _NEUTRAL_MIN_S,
                       shadow_v: int = 45, highlight_v: int = 245) -> str:
    """Map a single OpenCV HSV triple to a human colour name."""
    if v <= shadow_v:
        return "black"
    if v >= highlight_v and s < low_s + 40:
        return "white"
    if s < low_s:
        return "grey"
    for h_lo, h_hi, s_lo, v_lo, v_hi, name, _hex in _PALETTE:
        if h_lo <= h <= h_hi and s >= s_lo and v_lo <= v <= v_hi:
            if name in {"orange", "yellow"} and s < 110 and v < 120:
                return "brown"
            return name
    # Fallbacks for out-of-range combos
    if s < low_s + 30:
        return "grey" if v < highlight_v else "white"
    if 8 <= h <= 25 and s >= 90 and v < 120:
        return "brown"
    return "unknown"


def _hex_for(name: str) -> str:
    for _h_lo, _h_hi, _s, _vlo, _vhi, n, hexval in _PALETTE:
        if n == name:
            return hexval
    return {
        "black": "#1a1a1a",
        "white": "#f5f5f5",
        "grey": "#9e9e9e",
        "brown": "#8d5a2b",
        "unknown": "#888888",
    }.get(name, "#888888")


def analyze_colour(
    image_bgr: np.ndarray,
    box: tuple[int, int, int, int],
    mask: np.ndarray | None = None,
    *,
    min_pixels: int = 400,
    saturation_low: int = 60,
    highlight_v: int = 245,
    shadow_v: int = 45,
    exclude_background: bool = True,
    top_n: int = 5,
) -> ColourResult:
    """Estimate the dominant colour of the product inside *box*.

    Parameters
    ----------
    image_bgr:
        Full decoded frame (BGR, as from OpenCV / ``cv2.imdecode``).
    box:
        Detection bounding box ``(x1, y1, x2, y2)``.
    mask:
        Optional boolean segmentation mask **already cropped to the box**
        (e.g. from a YOLO-seg model). When given, background exclusion is
        skipped in favour of the mask.
    """
    region = crop_region(image_bgr, box)
    if region.size == 0:
        return ColourResult(
            name="unknown",
            quality="poor",
            warnings=["Empty product region — colour could not be measured."],
        )

    h_img, w_img = region.shape[:2]
    pixel_count = h_img * w_img

    if mask is not None:
        usable = mask.astype(bool)
        if usable.shape[:2] != (h_img, w_img):
            usable = np.ones((h_img, w_img), dtype=bool)
    elif exclude_background:
        usable = _border_mask(region)
    else:
        usable = np.ones((h_img, w_img), dtype=bool)

    warnings: list[str] = []
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    hsv_px = hsv[usable]
    if hsv_px.shape[0] == 0:
        return ColourResult(
            name="unknown",
            quality="poor",
            pixel_count=pixel_count,
            warnings=["No usable pixels in the product region."],
        )

    hues = hsv_px[:, 0].astype(np.int32)
    sats = hsv_px[:, 1].astype(np.float32)
    vals = hsv_px[:, 2].astype(np.float32)
    n = int(hues.shape[0])

    mean_s = float(sats.mean())
    mean_v = float(vals.mean())
    low_light = mean_v < 70
    overexposed = mean_v > 225 and float((vals > 245).mean()) > 0.45

    if n < min_pixels:
        warnings.append(
            f"Product region is small ({n} px) — colour estimate is less reliable."
        )
    if low_light:
        warnings.append("Low lighting detected — colour may be inaccurate.")
    if overexposed:
        warnings.append("Region appears overexposed — colour may be inaccurate.")
    if mean_s < _NEUTRAL_MIN_S:
        warnings.append("Low saturation — region looks neutral/greyish.")

    # Histogram of names
    counts: dict[str, int] = {}
    for h, s, v in zip(hues.tolist(), sats.astype(int).tolist(), vals.astype(int).tolist()):
        name = name_for_hsv_pixel(h, s, v, _NEUTRAL_MIN_S, shadow_v, highlight_v)
        counts[name] = counts.get(name, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    total = float(sum(counts.values())) or 1.0
    distribution = {k: v / total for k, v in ranked[: max(top_n, 1)]}
    dominant, dom_count = ranked[0]
    dom_share = dom_count / total

    # Quality grading
    if n >= min_pixels and not low_light and not overexposed and mean_s >= _NEUTRAL_MIN_S and dom_share >= 0.4:
        quality = "good"
    elif n >= min_pixels // 2 and not low_light and not overexposed:
        quality = "fair"
    else:
        quality = "poor"
    reliable = quality in {"good", "fair"}

    if not reliable:
        warnings.append("Colour result is unreliable — treat as indicative only.")

    # Normalise to L* 0..100 and a*/b* centred on 0 — the same convention as
    # rgb_hex_to_lab(), so delta_e comparisons are meaningful.
    sample_bgr = hsv_px_to_bgr_sample(hues, sats, vals)
    raw_lab = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(axis=0)
    lab_mean = (
        float(raw_lab[0]) * 100.0 / 255.0,
        float(raw_lab[1]) - 128.0,
        float(raw_lab[2]) - 128.0,
    )

    return ColourResult(
        name=dominant,
        hex_value=_hex_for(dominant),
        distribution=distribution,
        quality=quality,
        warnings=warnings,
        pixel_count=n,
        mean_saturation=mean_s,
        mean_value=mean_v,
        mean_lab=lab_mean,
        reliable=reliable,
    )


def hsv_px_to_bgr_sample(hues: np.ndarray, sats: np.ndarray, vals: np.ndarray) -> np.ndarray:
    """Build a small representative BGR sample (subsampled) for Lab averaging."""
    step = max(1, hues.shape[0] // 512)
    sample_hsv = np.stack(
        [hues[::step].astype(np.uint8), sats[::step].astype(np.uint8), vals[::step].astype(np.uint8)],
        axis=1,
    ).reshape(-1, 1, 3)
    return cv2.cvtColor(sample_hsv, cv2.COLOR_HSV2BGR)


# --------------------------------------------------------------------------- comparison
def rgb_hex_to_lab(hex_value: str) -> tuple[float, float, float]:
    hex_value = hex_value.lstrip("#")
    if len(hex_value) != 6:
        return (0.0, 0.0, 0.0)
    bgr = np.uint8([[[int(hex_value[4:6], 16), int(hex_value[2:4], 16), int(hex_value[0:2], 16)]]])
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0, 0]
    # Normalise to L* 0..100, a*/b* roughly -128..127
    return (float(lab[0]) * 100.0 / 255.0, float(lab[1]) - 128.0, float(lab[2]) - 128.0)


def delta_e76(lab1: Iterable[float], lab2: Iterable[float]) -> float:
    """CIE76 colour difference between two Lab colours."""
    l1, a1, b1 = (float(x) for x in lab1)
    l2, a2, b2 = (float(x) for x in lab2)
    return float(((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5)


def colour_similarity(result: ColourResult, accepted_hex: str) -> float:
    """Map a Lab ΔE to a 0..1 similarity score (1 = identical, 0 = far apart)."""
    if not accepted_hex or result.name == "unknown":
        return 0.0
    try:
        de = delta_e76(result.mean_lab, rgb_hex_to_lab(accepted_hex))
    except Exception:  # pragma: no cover - defensive
        return 0.0
    return max(0.0, min(1.0, 1.0 - de / 60.0))


def similarity_to_names(result: ColourResult, accepted: Iterable[str]) -> float:
    """Best similarity against a list of accepted colour *names* (heuristic)."""
    accepted = [a.strip().lower() for a in accepted if a and a.strip()]
    if not accepted:
        return 0.0
    if result.name.lower() in accepted:
        return max(0.7, _hex_similarity_bonus(result, accepted))
    # near-name matches (e.g. "dark blue" vs "blue")
    for a in accepted:
        if a in result.name or result.name in a:
            return 0.6
    return 0.15


def analyse_similarity_to_accepted(
    result: ColourResult, accepted: list[tuple[str, str]]
) -> float:
    """Best 0..1 similarity against ``[(colour_name, hex_value), ...]``.

    Combines name matching with a CIELAB ΔE comparison when hex values exist.
    """
    if not accepted or result.name == "unknown":
        return 0.0
    best = 0.0
    result_name = result.name.lower()
    for name, hexval in accepted:
        n = (name or "").strip().lower()
        if n:
            if result_name == n:
                best = max(best, 0.85)
            elif n in result_name or result_name in n:
                best = max(best, 0.65)
        if hexval:
            best = max(best, colour_similarity(result, hexval))
    return best


def _hex_similarity_bonus(result: ColourResult, accepted: list[str]) -> float:
    best = 0.7
    for name in accepted:
        hexval = _hex_for(name)
        if hexval.startswith("#"):
            best = max(best, colour_similarity(result, hexval))
    return best


def named_colour_palette() -> list[dict]:
    """Palette exposed by the API for UI colour pickers."""
    seen: dict[str, str] = {}
    for _h1, _h2, _s, _vl, _vh, name, hexval in _PALETTE:
        seen.setdefault(name, hexval)
    seen.update({"black": "#1a1a1a", "white": "#f5f5f5", "grey": "#9e9e9e", "brown": "#8d5a2b"})
    return [{"name": k, "hex": v} for k, v in seen.items()]
