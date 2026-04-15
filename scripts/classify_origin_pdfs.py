from __future__ import annotations

import argparse
import multiprocessing as mp
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.integrations.pdf_classifier import PdfClassifier


DEFAULT_SOURCE_DIR = Path("standards/orgin")
DEFAULT_OUTPUT_PATH = Path("standards/orgin_pdf_classification.txt")
DEFAULT_TIMEOUT_SECONDS = 20


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify PDFs in standards/orgin and write key=value results.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Directory containing PDFs to classify.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output text file path.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Per-file timeout seconds.")
    return parser


def _classify_worker(pdf_path: str, queue: mp.Queue) -> None:
    with open(os.devnull, "w", encoding="utf-8") as null_handle:
        sys.stdout = null_handle
        sys.stderr = null_handle
        result = PdfClassifier().classify(pdf_path)
    queue.put(result.to_dict())


def _quality_grade(result: dict[str, object]) -> str:
    pdf_type = str(result.get("pdf_type") or "")
    if pdf_type in {"encrypted_pdf", "unreadable_pdf", "failed_pdf", "timeout_pdf"}:
        return "F"

    digital_ratio = float(result.get("digital_page_ratio") or 0.0)
    nonempty_ratio = float(result.get("nonempty_page_ratio") or 0.0)
    weird_ratio = float(result.get("avg_weird_ratio") or 0.0)

    if pdf_type == "digital_pdf" and digital_ratio >= 0.9 and weird_ratio <= 0.05:
        return "A"
    if pdf_type == "digital_pdf" and nonempty_ratio >= 0.8 and weird_ratio <= 0.12:
        return "B"
    if pdf_type == "hybrid_pdf":
        return "C"
    if pdf_type in {"scanned_pdf", "textless_pdf"}:
        return "D"
    return "E"


def _suggested_action(result: dict[str, object]) -> str:
    pdf_type = str(result.get("pdf_type") or "")
    if pdf_type == "digital_pdf":
        return "直接索引"
    if pdf_type == "hybrid_pdf":
        return "按页 OCR"
    if pdf_type in {"scanned_pdf", "textless_pdf"}:
        return "整本 OCR"
    if pdf_type == "encrypted_pdf":
        return "解密或更换文件"
    if pdf_type == "timeout_pdf":
        return "延长超时或单独处理"
    return "人工检查"


def _format_ratio(value: object) -> str:
    return f"{float(value or 0.0):.1%}"


def _format_float(value: object) -> str:
    return f"{float(value or 0.0):.2f}"


def main() -> int:
    args = _build_parser().parse_args()
    source_dir = Path(args.source_dir)
    output_path = Path(args.output)
    timeout_seconds = max(1, int(args.timeout))

    if not source_dir.exists():
        raise SystemExit(f"source_dir_not_found:{source_dir}")

    pdf_paths = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for path in pdf_paths:
            queue: mp.Queue = mp.Queue(maxsize=1)
            process = mp.Process(target=_classify_worker, args=(str(path), queue))
            process.start()
            process.join(timeout_seconds)
            if process.is_alive():
                process.terminate()
                process.join()
                result = {
                    "file_name": path.name,
                    "pdf_type": "timeout_pdf",
                    "page_count": 0,
                    "nonempty_page_ratio": 0.0,
                    "digital_page_ratio": 0.0,
                    "avg_weird_ratio": 0.0,
                    "avg_meaningful_ratio": 0.0,
                    "avg_chars_per_page": 0.0,
                    "reason": "classification_timeout",
                }
            else:
                try:
                    result = dict(queue.get_nowait())
                except Exception:
                    result = {
                        "file_name": path.name,
                        "pdf_type": "failed_pdf",
                        "page_count": 0,
                        "nonempty_page_ratio": 0.0,
                        "digital_page_ratio": 0.0,
                        "avg_weird_ratio": 0.0,
                        "avg_meaningful_ratio": 0.0,
                        "avg_chars_per_page": 0.0,
                        "reason": "classification_failed",
                    }

            handle.write(f"文件={path.name}\n")
            handle.write(f"类型={result['pdf_type']}\n")
            handle.write(f"质量等级={_quality_grade(result)}\n")
            handle.write(f"建议动作={_suggested_action(result)}\n")
            handle.write(f"总页数={result['page_count']}\n")
            handle.write(f"非空页占比={_format_ratio(result['nonempty_page_ratio'])}\n")
            handle.write(f"高质量文本页占比={_format_ratio(result['digital_page_ratio'])}\n")
            handle.write(f"平均乱码占比={_format_ratio(result['avg_weird_ratio'])}\n")
            handle.write(f"平均有效字符占比={_format_ratio(result['avg_meaningful_ratio'])}\n")
            handle.write(f"平均每页字符数={_format_float(result['avg_chars_per_page'])}\n")
            handle.write(f"原因={result['reason']}\n")
            handle.write("\n")
            handle.flush()

    print(f"wrote {len(pdf_paths)} results to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
