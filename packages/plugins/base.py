from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from packages.core.models import NormalizedDocument


class DocumentProcessorPlugin(ABC):
    plugin_id: str = ""
    supported_types: tuple[str, ...] = ()

    @abstractmethod
    def can_handle(self, input_file: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def preprocess(self, input_file: Path, run_context: dict[str, Any]) -> NormalizedDocument:
        raise NotImplementedError

    def metadata(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "supported_types": list(self.supported_types),
        }
