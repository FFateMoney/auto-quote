from __future__ import annotations

from pathlib import Path

from backendV2.core.settings import Settings


def resolve_run_dir(settings: Settings, value: str | Path) -> Path:
    candidate = Path(value).resolve()
    runs_root = settings.agent_runs_root.resolve()
    if not candidate.is_dir() or not candidate.is_relative_to(runs_root):
        raise ValueError("run_dir must be an existing directory inside agent_workspace/runtime")
    return candidate


def resolve_run_file(run_dir: Path, value: str | Path) -> Path:
    candidate = Path(value)
    resolved = (run_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if not resolved.is_relative_to(run_dir.resolve()):
        raise ValueError("file must be inside the current run directory")
    return resolved
