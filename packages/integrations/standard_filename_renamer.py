from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from packages.core.models import StandardDocumentRecord

from .settings import get_settings
from .standard_library import normalize_standard_key
from .standard_store import StandardIndexStore


logger = logging.getLogger(__name__)
WINDOW_SIZES = (1, 2, 3)
MAX_CANDIDATE_LINES = 18
NOISE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bpage\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bdisclaimer\b", re.IGNORECASE),
    re.compile(r"版权所有|目录|目次"),
)
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')


@dataclass(slots=True)
class RenameSuggestion:
    relative_path: str
    current_name: str
    suggested_name: str
    score: float
    source_text: str


class StandardFilenameRenamer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = StandardIndexStore(self.settings.standard_index_dir, debug=self.settings.standard_index_debug)
        self.output_path = self.settings.standard_index_dir / "rename_candidates.txt"

    def generate_mapping(self, *, output_path: Path | None = None) -> list[RenameSuggestion]:
        output = output_path or self.output_path
        suggestions: list[RenameSuggestion] = []
        for record in self.store.load_manifest().documents:
            suggestion = self._suggest_for_record(record)
            if suggestion is None:
                continue
            suggestions.append(suggestion)

        suggestions.sort(key=lambda item: (-item.score, item.relative_path))
        self._write_mapping(output, suggestions)
        logger.info("标准重命名映射生成完成 | output=%s | suggestions=%s", output, len(suggestions))
        return suggestions

    def apply_mapping(self, *, mapping_path: Path | None = None) -> int:
        mapping_file = mapping_path or self.output_path
        operations = self._read_mapping(mapping_file)
        applied = 0
        for relative_path, target_relative_path in operations:
            source = self.settings.standards_dir / relative_path
            target = self.settings.standards_dir / target_relative_path
            if not source.exists():
                logger.warning("标准重命名跳过 | source_missing=%s", relative_path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and source.resolve() != target.resolve():
                logger.warning("标准重命名跳过 | target_exists=%s", target_relative_path)
                continue
            source.rename(target)
            applied += 1
            logger.info("标准重命名完成 | %s -> %s", relative_path, target_relative_path)
        logger.info("标准重命名汇总 | applied=%s | mapping=%s", applied, mapping_file)
        return applied

    def _suggest_for_record(self, record: StandardDocumentRecord) -> RenameSuggestion | None:
        source_path = Path(record.path)
        current_name = source_path.name
        suffix = source_path.suffix
        relative_path = str(source_path.relative_to(self.settings.standards_dir))
        current_stem = source_path.stem

        page_lines = self._load_first_page_lines(record.doc_id)
        if not page_lines:
            return None

        best_text = ""
        best_score = 0.0
        for candidate in self._iter_candidate_windows(page_lines):
            score = self._score_candidate(
                candidate_text=candidate,
                current_name=current_stem,
                standard_code=record.standard_code,
                standard_key=record.standard_key or normalize_standard_key(record.standard_code),
            )
            if score <= best_score:
                continue
            best_score = score
            best_text = candidate

        if not best_text:
            return None

        suggested_stem = self._build_suggested_stem(
            candidate_text=best_text,
            current_stem=current_stem,
            standard_code=record.standard_code,
        )
        if not suggested_stem:
            return None
        suggested_name = f"{suggested_stem}{suffix}"
        if suggested_name == current_name:
            return None

        return RenameSuggestion(
            relative_path=relative_path,
            current_name=current_name,
            suggested_name=suggested_name,
            score=best_score,
            source_text=best_text,
        )

    def _load_first_page_lines(self, doc_id: str) -> list[str]:
        debug_path = self.settings.standard_index_dir / "debug" / doc_id / "cleaned_pages.json"
        if not debug_path.exists():
            return []
        try:
            pages = json.loads(debug_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not pages:
            return []
        first_page = str(pages[0] or "")
        lines = []
        for raw_line in first_page.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            lines.append(line)
        return lines[:MAX_CANDIDATE_LINES]

    def _iter_candidate_windows(self, lines: list[str]) -> list[str]:
        candidates: list[str] = []
        for index, line in enumerate(lines):
            if self._looks_like_noise(line):
                continue
            for window_size in WINDOW_SIZES:
                window = lines[index : index + window_size]
                if len(window) < window_size:
                    continue
                if any(self._looks_like_noise(item) for item in window):
                    continue
                merged = " ".join(window).strip()
                if merged:
                    candidates.append(merged)
        return list(dict.fromkeys(candidates))

    def _score_candidate(self, *, candidate_text: str, current_name: str, standard_code: str, standard_key: str) -> float:
        score = 0.0
        current_key = normalize_standard_key(current_name)
        candidate_key = normalize_standard_key(candidate_text)
        if current_key and candidate_key:
            score += SequenceMatcher(None, current_key, candidate_key).ratio() * 3.0
        if standard_key and standard_key in candidate_key:
            score += 2.5
        if standard_code and standard_code.lower() in candidate_text.lower():
            score += 1.5
        if re.search(r"[\u4e00-\u9fff]", candidate_text):
            score += 0.4
        if 6 <= len(candidate_text) <= 120:
            score += 0.3
        if self._looks_like_noise(candidate_text):
            score -= 2.0
        return score

    def _build_suggested_stem(self, *, candidate_text: str, current_stem: str, standard_code: str) -> str:
        text = re.sub(r"\s+", " ", candidate_text).strip(" -_.")
        text = INVALID_FILENAME_CHARS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip(" .")
        if not text:
            return ""

        standard_code = standard_code.strip()
        if standard_code:
            code_key = normalize_standard_key(standard_code)
            text_key = normalize_standard_key(text)
            if code_key and code_key not in text_key:
                text = f"{standard_code} {text}"

        current_key = normalize_standard_key(current_stem)
        text_key = normalize_standard_key(text)
        if current_key and text_key and current_key == text_key:
            return current_stem
        return text

    def _looks_like_noise(self, text: str) -> bool:
        clean = text.strip()
        if not clean:
            return True
        if len(clean) <= 2:
            return True
        if re.fullmatch(r"[\W_]+", clean):
            return True
        for pattern in NOISE_PATTERNS:
            if pattern.search(clean):
                return True
        return False

    def _write_mapping(self, path: Path, suggestions: list[RenameSuggestion]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Delete lines you do not want to rename.",
            "# Format: current_relative_path => target_relative_path",
            "# Score and source_text are comments for manual review.",
            "",
        ]
        for item in suggestions:
            target_relative = str(Path(item.relative_path).with_name(item.suggested_name))
            source_text = item.source_text.replace("\n", " ").replace("#", " ")
            lines.append(
                f"{item.relative_path} => {target_relative}  # score={item.score:.2f} source={source_text}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _read_mapping(self, path: Path) -> list[tuple[str, str]]:
        operations: list[tuple[str, str]] = []
        if not path.exists():
            return operations
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if "=>" not in line:
                continue
            source, target = [part.strip() for part in line.split("=>", 1)]
            if not source or not target or source == target:
                continue
            operations.append((source, target))
        return operations


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or apply standard filename rename suggestions.")
    parser.add_argument("--generate", action="store_true", help="Generate rename suggestions from indexed first-page text.")
    parser.add_argument("--apply", action="store_true", help="Apply rename suggestions from the mapping file.")
    parser.add_argument(
        "--mapping",
        type=Path,
        default=None,
        help="Optional mapping file path. Defaults to data/standard_index/rename_candidates.txt.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    args = _build_parser().parse_args()
    if not args.generate and not args.apply:
        args.generate = True

    tool = StandardFilenameRenamer()
    if args.generate:
        tool.generate_mapping(output_path=args.mapping)
    if args.apply:
        tool.apply_mapping(mapping_path=args.mapping)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
