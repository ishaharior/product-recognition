"""Single-command development launcher (optional convenience).

Starts the FastAPI backend and the Vite frontend together; Ctrl+C stops both.
The separate commands in README.md remain the primary, always-supported way.

Examples (run from the repository root):

    python scripts/run_dev.py                 # backend :8000 + frontend :5173
    python scripts/run_dev.py --backend-only  # API only
    python scripts/run_dev.py --frontend-only # dashboard only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run backend and frontend dev servers together.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    return parser


def _frontend_command(port: int) -> list[str]:
    if os_is_windows():
        return ["cmd", "/c", "npm", "run", "dev", "--", "--port", str(port)]
    return ["npm", "run", "dev", "--", "--port", str(port)]


def os_is_windows() -> bool:
    return sys.platform.startswith("win")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    procs: dict[str, subprocess.Popen[bytes]] = {}

    if not args.frontend_only:
        procs["backend"] = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "backend",
                "--port",
                str(args.backend_port),
            ],
            cwd=str(REPO_ROOT),
        )

    if not args.backend_only:
        node_modules = REPO_ROOT / "frontend" / "node_modules"
        if not node_modules.is_dir():
            print("frontend/node_modules missing — run `npm install` in frontend/ first.", file=sys.stderr)
            for p in procs.values():
                p.terminate()
            return 2
        if shutil.which("npm") is None:
            print("npm not found on PATH — install Node.js first.", file=sys.stderr)
            for p in procs.values():
                p.terminate()
            return 2
        procs["frontend"] = subprocess.Popen(
            _frontend_command(args.frontend_port), cwd=str(REPO_ROOT / "frontend")
        )

    urls = []
    if "backend" in procs:
        urls.append(f"API      → http://127.0.0.1:{args.backend_port}/api/health")
    if "frontend" in procs:
        urls.append(f"Dashboard→ http://localhost:{args.frontend_port}/")
    print("Smart Product Station dev launcher")
    for line in urls:
        print(f"  {line}")
    print("Press Ctrl+C to stop.\n")

    exit_code = 0
    try:
        while True:
            for name, proc in procs.items():
                code = proc.poll()
                if code is not None:
                    print(f"{name} exited with code {code}", file=sys.stderr)
                    exit_code = code or 1
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                proc.terminate()
        deadline = time.time() + 5
        for proc in procs.values():
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
