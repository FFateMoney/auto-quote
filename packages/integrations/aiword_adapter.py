from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from packages.core.logging_utils import append_run_log

from .settings import get_settings


logger = logging.getLogger(__name__)


def export_content_view(input_path: Path, output_dir: Path) -> dict:
    settings = get_settings()
    script_path = settings.aiword_script_path
    if not script_path.exists():
        raise RuntimeError(f"aiword_script_not_found:{script_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir.parents[1] if len(output_dir.parents) >= 2 else output_dir
    logger.info("AIWord 开始导出内容视图: input=%s output=%s", input_path.name, output_dir)
    append_run_log(run_dir, f"AIWord 开始导出内容视图: {input_path.name}")
    command = [
        sys.executable,
        str(script_path),
        "export-content",
        "-I",
        str(input_path),
        "-O",
        str(output_dir),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(script_path.parent.parent),
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        logger.error("AIWord 导出失败: input=%s detail=%s", input_path.name, detail or "unknown_error")
        append_run_log(run_dir, f"AIWord 导出失败: {input_path.name} | {detail or 'unknown_error'}")
        raise RuntimeError(f"aiword_export_failed:{input_path.name}:{detail or 'unknown_error'}")

    result_path = output_dir / f"{input_path.stem}.content_view.json"
    if not result_path.exists():
        raise RuntimeError(f"aiword_content_view_missing:{result_path}")
    logger.info("AIWord 导出完成: input=%s result=%s", input_path.name, result_path.name)
    append_run_log(run_dir, f"AIWord 导出完成: {input_path.name}")
    return json.loads(result_path.read_text(encoding="utf-8"))
