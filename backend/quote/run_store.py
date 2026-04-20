from __future__ import annotations

import json
from pathlib import Path

from backend.quote.models import RunState


class RunStore:
    def save(self, path: Path, state: RunState) -> None:
        state.touch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: Path) -> RunState:
        return RunState.model_validate(json.loads(path.read_text(encoding="utf-8")))
