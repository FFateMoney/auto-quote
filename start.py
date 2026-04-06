from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"missing_config: {CONFIG_PATH}")
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def stream_output(process: subprocess.Popen[str], prefix: str) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{prefix}] {line.rstrip()}", flush=True)


def terminate_process(process: subprocess.Popen[str] | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"停止{name}...", flush=True)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    config = load_config()
    startup = nested(config, "startup", default={}) or {}

    backend_host = str(startup.get("backend_host") or "127.0.0.1")
    backend_port = int(startup.get("backend_port") or 8000)
    frontend_host = str(startup.get("frontend_host") or "127.0.0.1")
    frontend_port = int(startup.get("frontend_port") or 5173)
    auto_open_browser = bool(startup.get("auto_open_browser", False))

    backend_url = f"http://{backend_host}:{backend_port}"
    frontend_url = f"http://{frontend_host}:{frontend_port}"

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "apps.api.main:app",
        "--reload",
        "--host",
        backend_host,
        "--port",
        str(backend_port),
    ]
    frontend_cmd = [
        "npm",
        "run",
        "web:dev",
        "--",
        "--host",
        frontend_host,
        "--port",
        str(frontend_port),
    ]

    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE_URL"] = f"{backend_url}/api"

    print("启动 Auto Quote...", flush=True)
    print(f"后端地址: {backend_url}", flush=True)
    print(f"前端地址: {frontend_url}", flush=True)
    print(f"前端 API 地址: {frontend_env['VITE_API_BASE_URL']}", flush=True)

    backend_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None

    def shutdown(*_: object) -> None:
        terminate_process(frontend_process, "前端")
        terminate_process(backend_process, "后端")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        backend_process = subprocess.Popen(
            backend_cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=stream_output, args=(backend_process, "api"), daemon=True).start()

        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=PROJECT_ROOT,
            env=frontend_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=stream_output, args=(frontend_process, "web"), daemon=True).start()

        if auto_open_browser:
            time.sleep(2)
            webbrowser.open(frontend_url)

        while True:
            backend_code = backend_process.poll()
            frontend_code = frontend_process.poll()
            if backend_code is not None:
                print(f"后端进程已退出，code={backend_code}", flush=True)
                terminate_process(frontend_process, "前端")
                return backend_code
            if frontend_code is not None:
                print(f"前端进程已退出，code={frontend_code}", flush=True)
                terminate_process(backend_process, "后端")
                return frontend_code
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("收到中断信号，正在停止服务...", flush=True)
        terminate_process(frontend_process, "前端")
        terminate_process(backend_process, "后端")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
