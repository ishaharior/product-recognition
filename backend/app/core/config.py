"""Application configuration.

All settings can be overridden through environment variables (optionally loaded
from a repository-root ``.env`` file). Machine-specific values are never
hardcoded; see ``.env.example`` at the repository root.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Make the repository root importable so `src.*` modules resolve no matter how
# the server is launched (uvicorn/pytest/scripts).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional
        return
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key} must be an integer, got {raw!r}") from exc


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key} must be a number, got {raw!r}") from exc


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the Smart Product Station backend."""

    # Paths
    repo_root: Path = REPO_ROOT
    models_dir: Path = field(default_factory=lambda: REPO_ROOT / "models")
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    sample_images_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "sample")
    db_path: Path = field(default_factory=lambda: REPO_ROOT / "backend" / "smart_station.db")
    product_spec_csv: Path = field(
        default_factory=lambda: REPO_ROOT / "data" / "product_specs.csv"
    )
    dataset_config_path: Path = field(
        default_factory=lambda: REPO_ROOT / "data" / "dataset_config.yaml"
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    # Inference: "baseline" | "custom" | "demo"
    inference_mode: str = "baseline"
    preload_model: bool = True
    baseline_weights: str = "yolo11n.pt"  # resolved against models_dir, then ultralytics assets
    custom_weights: str = ""  # path relative to repo root or absolute
    confidence_threshold: float = 0.35
    unknown_confidence_threshold: float = 0.50
    max_frame_width: int = 640
    max_frame_height: int = 640
    max_incoming_fps: int = 8
    detection_queue_size: int = 2

    # Colour analysis
    colour_min_region_pixels: int = 400
    colour_saturation_low: int = 60  # HSV S below -> neutral/greyish
    colour_highlight_v: int = 245
    colour_shadow_v: int = 45

    # Weight sensor
    sensor_backend: str = "mock"  # "mock" | "serial" | "disabled"
    sensor_port: str = ""
    sensor_baudrate: int = 9600
    sensor_timeout_s: float = 3.0
    sensor_stability_delta_g: float = 2.0
    sensor_stability_samples: int = 5
    sensor_stability_window_s: float = 1.5

    # Verification thresholds
    verify_min_confidence: float = 0.45
    verify_weight_tolerance_pct: float = 10.0
    verify_colour_min_similarity: float = 0.45
    verify_stable_weight_required: bool = True

    # Demo mode
    demo_tick_ms: int = 900
    store_frames: bool = False  # never store camera frames by default

    # Misc
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def baseline_weights_path(self) -> Path | None:
        """Resolve baseline weights to a local file if present, else None."""
        candidate = self.models_dir / self.baseline_weights
        if candidate.exists():
            return candidate
        return None

    @property
    def custom_weights_path(self) -> Path | None:
        if not self.custom_weights:
            return None
        path = Path(self.custom_weights)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path if path.exists() else None


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the current environment."""
    _load_dotenv()
    origins = tuple(
        o.strip()
        for o in _env_str(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    )
    db_path = Path(_env_str("DB_PATH", str(REPO_ROOT / "backend" / "smart_station.db")))
    return Settings(
        host=_env_str("APP_HOST", "127.0.0.1"),
        port=_env_int("APP_PORT", 8000),
        cors_origins=origins,
        db_path=db_path,
        inference_mode=_env_str("INFERENCE_MODE", "baseline").strip().lower(),
        preload_model=_env_bool("PRELOAD_MODEL", True),
        baseline_weights=_env_str("BASELINE_WEIGHTS", "yolo11n.pt"),
        custom_weights=_env_str("CUSTOM_WEIGHTS", ""),
        confidence_threshold=_env_float("CONFIDENCE_THRESHOLD", 0.35),
        unknown_confidence_threshold=_env_float("UNKNOWN_CONFIDENCE_THRESHOLD", 0.50),
        max_frame_width=_env_int("MAX_FRAME_WIDTH", 640),
        max_frame_height=_env_int("MAX_FRAME_HEIGHT", 640),
        max_incoming_fps=_env_int("MAX_INCOMING_FPS", 8),
        sensor_backend=_env_str("SENSOR_BACKEND", "mock").strip().lower(),
        sensor_port=_env_str("SENSOR_PORT", ""),
        sensor_baudrate=_env_int("SENSOR_BAUDRATE", 9600),
        sensor_timeout_s=_env_float("SENSOR_TIMEOUT_S", 3.0),
        verify_min_confidence=_env_float("VERIFY_MIN_CONFIDENCE", 0.45),
        verify_weight_tolerance_pct=_env_float("VERIFY_WEIGHT_TOLERANCE_PCT", 10.0),
        verify_colour_min_similarity=_env_float("VERIFY_COLOUR_MIN_SIMILARITY", 0.45),
        demo_tick_ms=_env_int("DEMO_TICK_MS", 900),
        store_frames=_env_bool("STORE_FRAMES", False),
        log_level=_env_str("LOG_LEVEL", "INFO").strip().upper(),
    )


settings = load_settings()
