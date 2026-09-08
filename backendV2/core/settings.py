from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _load_config() -> dict[str, Any]:
    config_path = Path(os.environ.get("AUTO_QUOTE_CONFIG_PATH", PROJECT_ROOT / "backend" / "dev" / "config.yaml"))
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    core_runtime_root: Path
    agent_workspace_root: Path
    agent_executable: str
    agent_profile: str
    qwen_api_key: str
    database: dict[str, Any]

    @property
    def agent_prompts_root(self) -> Path:
        return self.agent_workspace_root / "prompts"

    @property
    def agent_codex_home(self) -> Path:
        return Path(os.environ.get("QUOTE_V2_CODEX_HOME", self.agent_workspace_root / "codex_home"))

    @property
    def agent_runs_root(self) -> Path:
        return self.agent_workspace_root / "runtime"

    @property
    def test_type_schemas_root(self) -> Path:
        return self.project_root / "backendV2" / "core" / "test_type_schemas"

    @classmethod
    def from_environment(cls) -> "Settings":
        config = _load_config()
        backend_root = PROJECT_ROOT / "backendV2"
        return cls(
            project_root=PROJECT_ROOT,
            core_runtime_root=Path(os.environ.get("QUOTE_V2_CORE_RUNTIME", backend_root / "core" / "runtime")),
            agent_workspace_root=Path(os.environ.get("QUOTE_V2_AGENT_WORKSPACE", backend_root / "agent_workspace")),
            agent_executable=os.environ.get(
                "QUOTE_V2_AGENT_EXECUTABLE",
                str(backend_root / "agent_runtime" / "codex" / "node_modules" / ".bin" / "codex"),
            ),
            agent_profile=os.environ.get("QUOTE_V2_AGENT_PROFILE", "quote-agent"),
            qwen_api_key=os.environ.get("QWEN_API_KEY") or str(_nested(config, "qwen", "api_key", default="")),
            database=dict(_nested(config, "database", default={}) or {}),
        )
