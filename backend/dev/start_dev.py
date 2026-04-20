from __future__ import annotations

import signal
import subprocess
import sys
import time

from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.config import PROJECT_ROOT
from backend.ocr.settings import get_settings as get_ocr_settings
from backend.quote.settings import get_settings as get_quote_settings


def main() -> int:
    repo_root = PROJECT_ROOT
    frontend_root = repo_root / "frontend" / "web"
    ocr = get_ocr_settings()
    quote = get_quote_settings()
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.ocr.http.app:app",
                "--host",
                ocr.host,
                "--port",
                str(ocr.port),
            ],
            cwd=repo_root,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.quote.http.app:app",
                "--host",
                quote.host,
                "--port",
                str(quote.port),
            ],
            cwd=repo_root,
        ),
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=frontend_root,
        ),
    ]

    def shutdown(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            dead = [process for process in processes if process.poll() is not None]
            if dead:
                return dead[0].returncode or 0
            time.sleep(1)
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
