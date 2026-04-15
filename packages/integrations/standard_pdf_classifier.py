from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .pdf_classifier import PdfClassificationResult, PdfClassifier


DEFAULT_SOURCE_DIR = Path("standards/orgin")
DEFAULT_DIGITAL_DIR = Path("standards/digital")
DEFAULT_SCAN_DIR = Path("standards/scan")
DEFAULT_REPORT_PATH = Path("standards/classification_report.json")


@dataclass(slots=True)
class StandardPdfClassifier:
    source_dir: Path = DEFAULT_SOURCE_DIR
    digital_dir: Path = DEFAULT_DIGITAL_DIR
    scan_dir: Path = DEFAULT_SCAN_DIR
    report_path: Path = DEFAULT_REPORT_PATH
    link_mode: str = "symlink"

    def __post_init__(self) -> None:
        self.classifier = PdfClassifier()

    def classify_all(self) -> list[PdfClassificationResult]:
        self.digital_dir.mkdir(parents=True, exist_ok=True)
        self.scan_dir.mkdir(parents=True, exist_ok=True)

        results: list[PdfClassificationResult] = []
        for path in sorted(self.source_dir.glob("*.pdf")):
            result = self.classifier.classify(path)
            self._publish(path, bucket=result.target_bucket)
            results.append(result)

        payload = {
            "source_dir": str(self.source_dir),
            "digital_dir": str(self.digital_dir),
            "scan_dir": str(self.scan_dir),
            "link_mode": self.link_mode,
            "documents": [item.to_dict() for item in results],
        }
        self.report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return results

    def classify_pdf(self, path: Path) -> PdfClassificationResult:
        return self.classifier.classify(path)

    def _publish(self, source_path: Path, *, bucket: str) -> None:
        target_dir = self.digital_dir if bucket == "digital" else self.scan_dir
        other_dir = self.scan_dir if bucket == "digital" else self.digital_dir
        target_path = target_dir / source_path.name
        other_path = other_dir / source_path.name

        if other_path.exists() or other_path.is_symlink():
            other_path.unlink()

        if target_path.is_symlink():
            current = target_path.resolve()
            if current == source_path.resolve():
                return
            target_path.unlink()
        elif target_path.exists():
            target_path.unlink()

        if self.link_mode == "copy":
            shutil.copy2(source_path, target_path)
            return

        target_path.symlink_to(os.path.relpath(source_path, start=target_dir))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify standard PDFs by text extraction quality.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Directory containing original standard PDFs.")
    parser.add_argument("--digital-dir", default=str(DEFAULT_DIGITAL_DIR), help="Directory for good digital PDFs.")
    parser.add_argument("--scan-dir", default=str(DEFAULT_SCAN_DIR), help="Directory for PDFs that still need processing.")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH), help="Where to write the JSON classification report.")
    parser.add_argument(
        "--link-mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="Publish files to target directories as symlinks or copies.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    classifier = StandardPdfClassifier(
        source_dir=Path(args.source_dir),
        digital_dir=Path(args.digital_dir),
        scan_dir=Path(args.scan_dir),
        report_path=Path(args.report_path),
        link_mode=args.link_mode,
    )
    results = classifier.classify_all()
    summary = {
        "total": len(results),
        "digital": sum(1 for item in results if item.target_bucket == "digital"),
        "scan": sum(1 for item in results if item.target_bucket == "scan"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
