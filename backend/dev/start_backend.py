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
from backend.cleaning.settings import get_settings as get_cleaning_settings
from backend.indexing.settings import get_settings as get_indexing_settings

def main() -> int:
    repo_root = PROJECT_ROOT
    ocr = get_ocr_settings()
    quote = get_quote_settings()
    cleaning = get_cleaning_settings()
    indexing = get_indexing_settings()
    
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
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.cleaning.http.app:app",
                "--host",
                cleaning.host,
                "--port",
                str(cleaning.port),
            ],
            cwd=repo_root,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.indexing.http.app:app",
                "--host",
                indexing.host,
                "--port",
                str(indexing.port),
            ],
            cwd=repo_root,
        ),
    ]

    def shutdown(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        deadline = time.time() + 5
        for process in processes:
            if process.poll() is not None:
                continue
            timeout = max(0.0, deadline - time.time())
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
        for process in processes:
            if process.poll() is None:
                process.kill()

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
