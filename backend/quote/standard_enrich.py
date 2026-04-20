"""Progressive standard enrichment — extracted from the orchestrator.

Iterates over standard evidence scopes round-by-round, calling the LLM
to fill missing fields until all targets are covered or evidence is exhausted.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from backend.quote.form_ops import merge_rows
from backend.quote.models import FormRow

if TYPE_CHECKING:
    from backend.quote.llm.requester import QwenRequester


logger = logging.getLogger(__name__)


def progressive_enrich(
    rows: list[FormRow],
    *,
    target_fields_by_row: dict[str, list[str]],
    requester: "QwenRequester",
    run_dir: Path,
) -> tuple[list[FormRow], list[str]]:
    """Fill missing fields by iterating over standard evidence scopes.

    Returns the updated rows and a list of human-readable notes.
    """
    current = [r.model_copy(deep=True) for r in rows]
    remaining = {rid: list(fields) for rid, fields in target_fields_by_row.items() if fields}
    notes: list[str] = []

    max_scopes = max((len(r.standard_evidences) for r in current), default=0)

    for scope_idx in range(max_scopes):
        request_rows: list[FormRow] = []
        request_targets: dict[str, list[str]] = {}
        before_by_id: dict[str, FormRow] = {}

        for row in current:
            fields_left = remaining.get(row.row_id) or []
            if not fields_left or scope_idx >= len(row.standard_evidences):
                continue
            scoped = row.model_copy(deep=True)
            scoped.standard_evidences = [row.standard_evidences[scope_idx].model_copy(deep=True)]
            request_rows.append(scoped)
            request_targets[row.row_id] = list(fields_left)
            before_by_id[row.row_id] = row.model_copy(deep=True)

        if not request_rows:
            break

        scope_label = (
            request_rows[0].standard_evidences[0].section_id
            if len(request_rows) == 1
            else f"round-{scope_idx + 1}"
        )
        logger.info(
            "standard enrich | scope=%s rows=%s target_fields=%s",
            scope_label, len(request_rows),
            sum(len(f) for f in request_targets.values()),
        )

        result = requester.enrich_form_with_evidences(
            request_rows,
            target_fields_by_row=request_targets,
            run_dir=run_dir,
        )
        current = merge_rows(current, result.items)
        if result.summary:
            notes.append(f"第{scope_idx + 1}轮模型摘要：{result.summary}")

        after_by_id = {r.row_id: r for r in current}
        for rid, fields_left in list(remaining.items()):
            before = before_by_id.get(rid)
            after = after_by_id.get(rid)
            if before is None or after is None:
                continue
            filled = _newly_filled(before, after, fields_left)
            if filled:
                remaining[rid] = [f for f in fields_left if f not in filled]
                notes.append(f"{rid}: 第{scope_idx + 1}轮已补字段 {', '.join(filled)}")
            else:
                notes.append(f"{rid}: 第{scope_idx + 1}轮未补出新字段")
            if not remaining.get(rid):
                notes.append(f"{rid}: 标准补充目标字段已全部覆盖")

        if all(not fields for fields in remaining.values()):
            notes.append("标准补充已覆盖全部目标字段，提前结束")
            break

    for rid, fields in remaining.items():
        if fields:
            notes.append(f"{rid}: 范围扩展结束后仍缺字段 {', '.join(fields)}")

    return current, notes


def _newly_filled(before: FormRow, after: FormRow, candidates: list[str]) -> list[str]:
    return [
        f for f in candidates
        if _has_value(getattr(after, f, None)) and not _has_value(getattr(before, f, None))
    ]


def _has_value(value: object) -> bool:
    return value not in (None, "", [])
