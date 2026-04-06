from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from packages.core.logging_utils import append_run_log
from packages.core.models import FormRow, NormalizedDocument, StandardContextDecision, StandardEvidence

from .settings import get_settings


MODEL_FIELDS: tuple[str, ...] = (
    "row_id",
    "raw_test_type",
    "canonical_test_type",
    "standard_codes",
    "pricing_mode",
    "pricing_quantity",
    "repeat_count",
    "sample_length_mm",
    "sample_width_mm",
    "sample_height_mm",
    "sample_weight_kg",
    "required_temp_min",
    "required_temp_max",
    "required_humidity_min",
    "required_humidity_max",
    "required_temp_change_rate",
    "required_freq_min",
    "required_freq_max",
    "required_accel_min",
    "required_accel_max",
    "required_displacement_min",
    "required_displacement_max",
    "required_irradiance_min",
    "required_irradiance_max",
    "required_water_temp_min",
    "required_water_temp_max",
    "required_water_flow_min",
    "required_water_flow_max",
    "source_text",
    "conditions_text",
    "sample_info_text",
)

CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)
logger = logging.getLogger(__name__)
RANGE_FIELD_PAIRS: tuple[tuple[str, str], ...] = (
    ("required_temp_min", "required_temp_max"),
    ("required_humidity_min", "required_humidity_max"),
    ("required_freq_min", "required_freq_max"),
    ("required_accel_min", "required_accel_max"),
    ("required_displacement_min", "required_displacement_max"),
    ("required_irradiance_min", "required_irradiance_max"),
    ("required_water_temp_min", "required_water_temp_max"),
    ("required_water_flow_min", "required_water_flow_max"),
)


@dataclass(slots=True)
class ModelFillResult:
    items: list[FormRow]
    summary: str = ""
    raw_response: str = ""


def _load_prompts(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_example() -> dict[str, Any]:
    example = FormRow.schema_example()
    payload = {field: example.get(field, "" if field != "standard_codes" else []) for field in MODEL_FIELDS}
    payload["row_id"] = ""
    return {"items": [payload]}


def _rules_text(*, preserve_row_ids: bool) -> str:
    lines = [
        "1. 只输出 JSON，对象根节点必须是 items 数组。",
        "2. 一个测试项目对应一行，不要把同一项目重复拆成多行。",
        "3. `standard_codes` 必须是字符串数组，没有就给空数组。",
        "4. `sample_length_mm`、`sample_width_mm`、`sample_height_mm` 分别填写样品长宽高，未知时给 null。",
        "5. 数值字段只能填数字或 null，不要带单位。",
        "6. `source_text`、`conditions_text`、`sample_info_text` 使用简洁中文总结来源信息。",
        "7. 遇到无法确定的字段留空字符串、空数组或 null，不要编造。",
        "8. 如果文档写的是确定单值而不是范围，例如温度 80℃、湿度 95%RH、水温 25℃、流量 10L/min、辐照 800W/m2，就把对应的 min/max 两个字段都填成同一个值。",
        "9. 文中的 `[IMAGE_n]` 与图片输入一一对应，图片是文档插图，不是时间序列视频帧。",
        "10. `pricing_quantity` 表示单次执行的计价数量，例如 5 小时；`repeat_count` 表示相同测试需要重复执行的次数/工件数，例如 3 件样品各做一遍就填 3。",
    ]
    if preserve_row_ids:
        lines.append("11. 如果是在补全已有表格，必须尽量保留已有行的 `row_id`，并在原有行上补字段，不要新增重复行。")
    return "\n".join(lines)


def _flatten_stream_part(parts: list[Any]) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, str):
            chunks.append(part)
            continue
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
            continue
        text = getattr(part, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "".join(chunks)


def _strip_code_fence(text: str) -> str:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = CODE_FENCE_RE.sub("", clean).strip()
    return clean


def _extract_json_text(text: str) -> str:
    clean = _strip_code_fence(text)
    match = re.search(r"(\{.*\}|\[.*\])", clean, re.DOTALL)
    return match.group(1) if match else clean


def _normalize_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    if isinstance(payload.get("standard_codes"), str):
        text = str(payload["standard_codes"]).strip()
        payload["standard_codes"] = [text] if text else []
    if isinstance(payload.get("sample_dimensions_mm"), (str, list)):
        dims = re.findall(r"-?\d+(?:\.\d+)?", str(payload["sample_dimensions_mm"]))
        numbers = [float(value) for value in dims]
        if numbers:
            payload.setdefault("sample_length_mm", numbers[0])
        if len(numbers) > 1:
            payload.setdefault("sample_width_mm", numbers[1])
        if len(numbers) > 2:
            payload.setdefault("sample_height_mm", numbers[2])
        payload.pop("sample_dimensions_mm", None)
    for field_name in ("sample_length_mm", "sample_width_mm", "sample_height_mm"):
        value = payload.get(field_name)
        if isinstance(value, str):
            dims = re.findall(r"-?\d+(?:\.\d+)?", value)
            payload[field_name] = float(dims[0]) if dims else None
    for field_name in (
        "pricing_quantity",
        "repeat_count",
        "sample_weight_kg",
        "required_temp_min",
        "required_temp_max",
        "required_humidity_min",
        "required_humidity_max",
        "required_temp_change_rate",
        "required_freq_min",
        "required_freq_max",
        "required_accel_min",
        "required_accel_max",
        "required_displacement_min",
        "required_displacement_max",
        "required_irradiance_min",
        "required_irradiance_max",
        "required_water_temp_min",
        "required_water_temp_max",
        "required_water_flow_min",
        "required_water_flow_max",
    ):
        value = payload.get(field_name)
        if isinstance(value, str):
            dims = re.findall(r"-?\d+(?:\.\d+)?", value)
            payload[field_name] = float(dims[0]) if dims else None
    _mirror_single_value_ranges(payload)
    return payload


def _mirror_single_value_ranges(payload: dict[str, Any]) -> None:
    for min_field, max_field in RANGE_FIELD_PAIRS:
        min_value = payload.get(min_field)
        max_value = payload.get(max_field)
        if min_value is None and max_value is None:
            continue
        if min_value is None and max_value is not None:
            payload[min_field] = max_value
            continue
        if max_value is None and min_value is not None:
            payload[max_field] = min_value


class QwenRequester:
    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        prompts_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.qwen_model
        self.prompts = _load_prompts(prompts_path or settings.prompts_path)
        self.client = client or OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)

    def extract_form(self, documents: list[NormalizedDocument], *, run_dir: Path | None = None) -> ModelFillResult:
        if not documents:
            return ModelFillResult(items=[], summary="未收到可抽取文档")
        prompt = self.prompts["document_extract"]
        messages = self._build_messages(
            system_prompt=str(prompt["system"]),
            user_template=str(prompt["user"]),
            documents=documents,
            current_rows=None,
        )
        content = self._stream_text(messages, run_dir=run_dir, request_name="文档抽取")
        return self._parse_form_result(content)

    def enrich_form_with_evidences(
        self,
        current_rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]] | None = None,
        run_dir: Path | None = None,
    ) -> ModelFillResult:
        if not any(row.standard_evidences for row in current_rows):
            return ModelFillResult(items=[row.model_copy(deep=True) for row in current_rows], summary="无可补充标准证据")
        prompt = self.prompts["standard_enrich_with_evidences"]
        messages = self._build_evidence_messages(
            system_prompt=str(prompt["system"]),
            user_template=str(prompt["user"]),
            current_rows=current_rows,
            target_fields_by_row=target_fields_by_row or {},
        )
        content = self._stream_text(messages, run_dir=run_dir, request_name="标准证据补表")
        return self._parse_form_result(content)

    def judge_standard_context(
        self,
        row: FormRow,
        evidence: StandardEvidence,
        *,
        target_fields: list[str] | None = None,
        run_dir: Path | None = None,
    ) -> StandardContextDecision:
        prompt = self.prompts["standard_context_judge"]
        messages = self._build_context_judge_messages(
            system_prompt=str(prompt["system"]),
            user_template=str(prompt["user"]),
            row=row,
            evidence=evidence,
            target_fields=target_fields or [],
        )
        content = self._stream_text(messages, run_dir=run_dir, request_name="标准上下文判定")
        return self._parse_standard_context_decision(content)

    def _build_messages(
        self,
        *,
        system_prompt: str,
        user_template: str,
        documents: list[NormalizedDocument],
        current_rows: list[FormRow] | None,
    ) -> list[dict[str, Any]]:
        manifest = self._document_manifest(documents)
        document_text = self._document_text(documents)
        schema_json = json.dumps(_schema_example(), ensure_ascii=False, indent=2)
        current_form = json.dumps(self._rows_for_model(current_rows or []), ensure_ascii=False, indent=2)
        user_text = (
            user_template.replace("$document_manifest", manifest)
            .replace("$document_text", document_text)
            .replace("$schema_json", schema_json)
            .replace("$rules_text", _rules_text(preserve_row_ids=current_rows is not None))
            .replace("$current_form", current_form)
        )

        content: list[dict[str, Any]] = []
        for document in documents:
            for asset in document.assets:
                content.append({"type": "image_url", "image_url": {"url": asset.data_url}})
        content.append({"type": "text", "text": user_text})
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]

    def _build_evidence_messages(
        self,
        *,
        system_prompt: str,
        user_template: str,
        current_rows: list[FormRow],
        target_fields_by_row: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        schema_json = json.dumps(_schema_example(), ensure_ascii=False, indent=2)
        current_form = json.dumps(self._rows_for_model(current_rows), ensure_ascii=False, indent=2)
        evidence_manifest, evidence_text = self._row_evidence_text(current_rows)
        target_manifest, target_text = self._row_target_fields_text(current_rows, target_fields_by_row)
        user_text = (
            user_template.replace("$current_form", current_form)
            .replace("$target_manifest", target_manifest)
            .replace("$target_text", target_text)
            .replace("$evidence_manifest", evidence_manifest)
            .replace("$evidence_text", evidence_text)
            .replace("$schema_json", schema_json)
            .replace("$rules_text", _rules_text(preserve_row_ids=True))
        )
        content = [{"type": "text", "text": user_text}]
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]

    def _build_context_judge_messages(
        self,
        *,
        system_prompt: str,
        user_template: str,
        row: FormRow,
        evidence: StandardEvidence,
        target_fields: list[str],
    ) -> list[dict[str, Any]]:
        current_row = json.dumps(self._rows_for_model([row]), ensure_ascii=False, indent=2)
        evidence_text = "\n".join(self._format_evidence_block(evidence))
        target_text = "\n".join(f"- {field}" for field in target_fields) if target_fields else "- (无明确目标字段)"
        user_text = (
            user_template.replace("$current_row", current_row)
            .replace("$evidence_text", evidence_text)
            .replace("$target_fields", target_text)
        )
        content = [{"type": "text", "text": user_text}]
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]

    def _document_manifest(self, documents: list[NormalizedDocument]) -> str:
        lines: list[str] = []
        for document in documents:
            lines.append(
                f"- {document.source_name} | kind={document.source_kind} | blocks={len(document.text_blocks)} | images={len(document.assets)}"
            )
        return "\n".join(lines) if lines else "- 无"

    def _document_text(self, documents: list[NormalizedDocument]) -> str:
        sections: list[str] = []
        for document in documents:
            block_text = "\n".join(block.text for block in document.text_blocks if block.text.strip()).strip()
            asset_lines = [
                f"- [{asset.asset_id}] position={asset.position} context={asset.context_text or '无'}"
                for asset in document.assets
            ]
            section = [
                f"## {document.source_name}",
                "正文：",
                block_text or "(空)",
            ]
            if asset_lines:
                section.extend(["插图说明：", *asset_lines])
            sections.append("\n".join(section).strip())
        return "\n\n".join(sections).strip()

    def _rows_for_model(self, rows: list[FormRow]) -> dict[str, Any]:
        return {"items": [{field: getattr(row, field) for field in MODEL_FIELDS} for row in rows]}

    def _row_evidence_text(self, rows: list[FormRow]) -> tuple[str, str]:
        manifest_lines: list[str] = []
        sections: list[str] = []
        for row in rows:
            evidences = row.standard_evidences
            row_label = row.raw_test_type or row.canonical_test_type or row.row_id
            manifest_lines.append(f"- row_id={row.row_id} | test={row_label} | evidence_count={len(evidences)}")
            section_lines = [f"## row_id={row.row_id} | test={row_label}"]
            if not evidences:
                section_lines.append("(无标准证据)")
                sections.append("\n".join(section_lines))
                continue
            for evidence in evidences:
                section_lines.extend(self._format_evidence_block(evidence))
            sections.append("\n".join(section_lines).strip())
        manifest = "\n".join(manifest_lines) if manifest_lines else "- 无"
        return manifest, "\n\n".join(sections).strip()

    def _row_target_fields_text(
        self,
        rows: list[FormRow],
        target_fields_by_row: dict[str, list[str]],
    ) -> tuple[str, str]:
        manifest_lines: list[str] = []
        sections: list[str] = []
        for row in rows:
            targets = target_fields_by_row.get(row.row_id) or []
            manifest_lines.append(f"- row_id={row.row_id} | target_fields={','.join(targets) if targets else '(无)'}")
            label = row.raw_test_type or row.canonical_test_type or row.row_id
            lines = [f"## row_id={row.row_id} | test={label}"]
            if not targets:
                lines.append("(无标准补充目标字段)")
            else:
                lines.append("仅允许补充以下字段：")
                lines.extend(f"- {field}" for field in targets)
            sections.append("\n".join(lines))
        manifest = "\n".join(manifest_lines) if manifest_lines else "- 无"
        return manifest, "\n\n".join(sections).strip()

    def _format_evidence_block(self, evidence: StandardEvidence) -> list[str]:
        reasons = "、".join(evidence.match_reasons) if evidence.match_reasons else "无"
        return [
            f"### {evidence.standard_code} | {evidence.section_id or evidence.chunk_id} | pages={evidence.page_start}-{evidence.page_end}",
            f"标题：{evidence.section_title or '无'}",
            f"匹配原因：{reasons}",
            "证据正文：",
            evidence.text.strip() or "(空)",
        ]

    def _stream_text(self, messages: list[dict[str, Any]], *, run_dir: Path | None, request_name: str) -> str:
        user_content = messages[1]["content"]
        image_count = sum(1 for item in user_content if item.get("type") == "image_url")
        text_length = len(str(user_content[-1].get("text") or "")) if user_content else 0
        logger.info("开始模型请求: stage=%s model=%s images=%s text_chars=%s", request_name, self.model, image_count, text_length)
        if run_dir is not None:
            append_run_log(run_dir, f"开始模型请求: {request_name} | model={self.model} | images={image_count} | text_chars={text_length}")
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=4000,
            modalities=["text"],
            stream=True,
            stream_options={"include_usage": True},
        )
        parts: list[str] = []
        chunk_count = 0
        for chunk in completion:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if isinstance(content, str):
                parts.append(content)
                chunk_count += 1
            elif isinstance(content, list):
                parts.append(_flatten_stream_part(content))
                chunk_count += 1
        text = "".join(part for part in parts if part)
        if not text.strip():
            logger.error("模型请求为空响应: stage=%s model=%s", request_name, self.model)
            if run_dir is not None:
                append_run_log(run_dir, f"模型请求失败: {request_name} | empty_response")
            raise RuntimeError("qwen_empty_response")
        logger.info("模型请求成功，处理中: stage=%s chunks=%s response_chars=%s", request_name, chunk_count, len(text))
        if run_dir is not None:
            append_run_log(run_dir, f"模型请求成功，处理中: {request_name} | chunks={chunk_count} | response_chars={len(text)}")
        return text

    def _parse_form_result(self, content: str) -> ModelFillResult:
        payload = json.loads(_extract_json_text(content))
        if isinstance(payload, list):
            raw_items = payload
            summary = ""
        else:
            raw_items = payload.get("items") or []
            summary = str(payload.get("document_summary") or payload.get("summary") or "").strip()

        items: list[FormRow] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_item_payload(item)
            items.append(FormRow.model_validate(normalized))
        logger.info("模型响应解析完成: rows=%s summary=%s", len(items), summary or "-")
        return ModelFillResult(items=items, summary=summary, raw_response=content)

    def _parse_standard_context_decision(self, content: str) -> StandardContextDecision:
        payload = json.loads(_extract_json_text(content))
        if not isinstance(payload, dict):
            raise RuntimeError("invalid_standard_context_decision")
        decision = StandardContextDecision.model_validate(payload)
        logger.info("标准上下文判定完成: decision=%s reason=%s", decision.decision, decision.reason or "-")
        return decision
