from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.quote.models import FormRow, StandardContextDecision, StandardEvidence

if TYPE_CHECKING:
    from backend.quote.llm.requester import QwenRequester


@dataclass(slots=True)
class StandardContextJudge:
    requester: QwenRequester = field(default_factory=lambda: _default_requester())

    def judge(
        self,
        row: FormRow,
        evidence: StandardEvidence,
        *,
        target_fields: list[str] | None = None,
        run_dir: Path | None = None,
    ) -> StandardContextDecision:
        return self.requester.judge_standard_context(
            row,
            evidence,
            target_fields=target_fields or [],
            run_dir=run_dir,
        )


def _default_requester() -> QwenRequester:
    from backend.quote.llm.requester import QwenRequester
    return QwenRequester()
