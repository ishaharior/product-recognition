"""Root pytest configuration: make `app` and `src` importable, set test env.

Environment variables are set BEFORE the application is imported anywhere so
the singleton Settings picks up an isolated test database and skips loading
heavy YOLO weights unless a test asks for them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("DB_PATH", str(BACKEND / "test_smart_station.db"))
os.environ.setdefault("PRELOAD_MODEL", "false")
os.environ.setdefault("SENSOR_BACKEND", "mock")
os.environ.setdefault("INFERENCE_MODE", "baseline")
os.environ.setdefault("DEMO_TICK_MS", "100000")  # ticker effectively idle in tests
