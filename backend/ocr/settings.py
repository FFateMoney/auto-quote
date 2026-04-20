from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from pathlib import Path

from backend.common.config import PROJECT_ROOT, as_bool, load_config, nested, resolve_path


def _as_list(value: object, *, default: list[str]) -> list[str]:
    if value in (None, ""):
        return list(default)
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return list(default)
    return [part.strip() for part in text.split(",") if part.strip()]


_DEFAULT_IGNORE_LABELS = ["number", "footnote", "header", "header_image", "footer", "footer_image", "aside_text"]


@dataclass(slots=True)
class OcrSettings:
    host: str
    port: int
    origin_dir: Path
    output_dir: Path
    device: str
    text_detection_model: str
    text_recognition_model: str
    use_region_detection: bool
    use_table_recognition: bool
    format_block_content: bool
    markdown_ignore_labels: list[str]
    use_doc_orientation_classify: bool
    use_doc_unwarping: bool
    use_textline_orientation: bool
    use_seal_recognition: bool
    use_formula_recognition: bool
    use_chart_recognition: bool
    use_table_orientation_classify: bool


@lru_cache(maxsize=1)
def get_settings() -> OcrSettings:
    cfg = load_config()

    def _s(env_key: str, *config_keys: str, default: object = None) -> object:
        v = os.environ.get(env_key)
        if v is not None:
            return v
        value = nested(cfg, "services", "ocr", *config_keys, default=None)
        if value is not None:
            return value
        return nested(cfg, "services", "ocr_service", *config_keys, default=default)

    def _structure(
        env_key: str,
        modern_key: str,
        legacy_key: str,
        *,
        default: object = None,
    ) -> object:
        value = _s(env_key, modern_key, default=None)
        if value is not None:
            return value
        return _s(env_key, legacy_key, default=default)

    return OcrSettings(
        host=str(_s("OCR_HOST", "host", default="127.0.0.1")).strip(),
        port=int(_s("OCR_PORT", "port", default=8001)),
        origin_dir=resolve_path(PROJECT_ROOT, _s("OCR_ORIGIN_DIR", "origin_dir"), fallback=PROJECT_ROOT / "data" / "origin"),
        output_dir=resolve_path(PROJECT_ROOT, _s("OCR_OUTPUT_DIR", "output_dir"), fallback=PROJECT_ROOT / "data" / "ocr_markdown"),
        device=str(_structure("OCR_DEVICE", "device", "pp_structure_device", default="gpu:0")).strip(),
        text_detection_model=str(
            _structure(
                "OCR_TEXT_DETECTION_MODEL",
                "text_detection_model",
                "pp_structure_text_detection_model_name",
                default="PP-OCRv5_server_det",
            )
        ).strip(),
        text_recognition_model=str(
            _structure(
                "OCR_TEXT_RECOGNITION_MODEL",
                "text_recognition_model",
                "pp_structure_text_recognition_model_name",
                default="PP-OCRv5_server_rec",
            )
        ).strip(),
        use_region_detection=as_bool(
            _structure("OCR_USE_REGION_DETECTION", "use_region_detection", "pp_structure_use_region_detection"),
            default=True,
        ),
        use_table_recognition=as_bool(
            _structure("OCR_USE_TABLE_RECOGNITION", "use_table_recognition", "pp_structure_use_table_recognition"),
            default=True,
        ),
        format_block_content=as_bool(
            _structure("OCR_FORMAT_BLOCK_CONTENT", "format_block_content", "pp_structure_format_block_content"),
            default=True,
        ),
        markdown_ignore_labels=_as_list(
            _structure("OCR_MARKDOWN_IGNORE_LABELS", "markdown_ignore_labels", "pp_structure_markdown_ignore_labels"),
            default=_DEFAULT_IGNORE_LABELS,
        ),
        use_doc_orientation_classify=as_bool(
            _structure(
                "OCR_USE_DOC_ORIENTATION_CLASSIFY",
                "use_doc_orientation_classify",
                "pp_structure_use_doc_orientation_classify",
            ),
            default=False,
        ),
        use_doc_unwarping=as_bool(
            _structure("OCR_USE_DOC_UNWARPING", "use_doc_unwarping", "pp_structure_use_doc_unwarping"),
            default=False,
        ),
        use_textline_orientation=as_bool(
            _structure("OCR_USE_TEXTLINE_ORIENTATION", "use_textline_orientation", "pp_structure_use_textline_orientation"),
            default=False,
        ),
        use_seal_recognition=as_bool(
            _structure("OCR_USE_SEAL_RECOGNITION", "use_seal_recognition", "pp_structure_use_seal_recognition"),
            default=False,
        ),
        use_formula_recognition=as_bool(
            _structure("OCR_USE_FORMULA_RECOGNITION", "use_formula_recognition", "pp_structure_use_formula_recognition"),
            default=False,
        ),
        use_chart_recognition=as_bool(
            _structure("OCR_USE_CHART_RECOGNITION", "use_chart_recognition", "pp_structure_use_chart_recognition"),
            default=False,
        ),
        use_table_orientation_classify=as_bool(
            _structure(
                "OCR_USE_TABLE_ORIENTATION_CLASSIFY",
                "use_table_orientation_classify",
                "pp_structure_use_table_orientation_classify",
            ),
            default=False,
        ),
    )
