from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class AgentExecution:
    return_code: int
    error: str = ""


class CodexAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(self, run_dir: Path, prompt_path: Path) -> AgentExecution:
        tools_bin = self._settings.project_root / "backendV2" / "core" / "tools" / "bin"
        workspace_root = self._settings.agent_workspace_root.resolve()
        relative_run_dir = run_dir.resolve().relative_to(workspace_root)
        environment = os.environ.copy()
        environment["PATH"] = f"{tools_bin}{os.pathsep}{environment.get('PATH', '')}"
        environment["PYTHONPATH"] = f"{self._settings.project_root}{os.pathsep}{environment.get('PYTHONPATH', '')}"
        environment["QUOTE_V2_CORE_PYTHON"] = sys.executable
        environment["CODEX_HOME"] = str(self._settings.agent_codex_home)
        if self._settings.qwen_api_key:
            environment["OPENAI_API_KEY"] = self._settings.qwen_api_key

        instruction = (
            f"阅读 {prompt_path}，这个文件是你的指导。"
            f"本次任务目录是 {relative_run_dir}；然后阅读该目录 input 中的文件并完成任务。"
        )
        command = [
            self._settings.agent_executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--profile",
            self._settings.agent_profile,
            "--config",
            f'model_catalog_json="{self._settings.agent_codex_home / "model-catalog.local.json"}"',
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "danger-full-access",
            "--json",
            "-C",
            str(workspace_root),
            instruction,
        ]
        log_path = run_dir / "agent_execution.jsonl"
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                completed = subprocess.run(
                    command,
                    cwd=run_dir,
                    env=environment,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
        except OSError as exc:
            message = str(exc)
            log_path.write_text(message + "\n", encoding="utf-8")
            return AgentExecution(return_code=127, error=message)
        return AgentExecution(return_code=completed.returncode)
