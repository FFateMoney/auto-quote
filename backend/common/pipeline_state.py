from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)

SYNC_STATE_DIRNAME = "sync_state"
LEGACY_CACHE_DIRNAME = ".cache"
MANIFEST_FILENAME = "sync_state.json"
LOCK_FILENAME = ".lock"
MANIFEST_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class PipelineRecord:
    source_hash: str
    output_relpaths: list[str] = field(default_factory=list)
    sink_ref: str | None = None
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_payload(cls, payload: object) -> "PipelineRecord | None":
        if not isinstance(payload, dict):
            return None
        source_hash = str(payload.get("source_hash") or "").strip()
        if not source_hash:
            return None
        output_relpaths_raw = payload.get("output_relpaths") or []
        if isinstance(output_relpaths_raw, list):
            output_relpaths = [str(item).strip() for item in output_relpaths_raw if str(item).strip()]
        else:
            output_relpaths = []
        sink_ref_raw = payload.get("sink_ref")
        sink_ref = None
        if sink_ref_raw is not None:
            sink_ref = str(sink_ref_raw).strip() or None
        updated_at = str(payload.get("updated_at") or "").strip() or utc_now_iso()
        return cls(
            source_hash=source_hash,
            output_relpaths=output_relpaths,
            sink_ref=sink_ref,
            updated_at=updated_at,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_hash": self.source_hash,
            "output_relpaths": list(self.output_relpaths),
            "sink_ref": self.sink_ref,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class PipelineManifest:
    stage: str
    input_root: str
    output_root: str | None
    records: dict[str, PipelineRecord] = field(default_factory=dict)
    version: int = MANIFEST_VERSION

    @classmethod
    def empty(cls, *, stage: str, input_root: Path, output_root: Path | None) -> "PipelineManifest":
        return cls(stage=stage, input_root=str(input_root), output_root=str(output_root) if output_root else None)

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        stage: str,
        input_root: Path,
        output_root: Path | None,
    ) -> "PipelineManifest":
        manifest = cls.empty(stage=stage, input_root=input_root, output_root=output_root)
        if not isinstance(payload, dict):
            return manifest
        manifest.version = int(payload.get("version") or MANIFEST_VERSION)
        manifest.stage = str(payload.get("stage") or stage)
        manifest.input_root = str(payload.get("input_root") or input_root)
        manifest.output_root = str(payload.get("output_root") or "") or (str(output_root) if output_root else None)
        records_raw = payload.get("records") or {}
        if isinstance(records_raw, dict):
            for key, value in records_raw.items():
                record = PipelineRecord.from_payload(value)
                if record is not None:
                    manifest.records[str(key)] = record
        return manifest

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "stage": self.stage,
            "input_root": self.input_root,
            "output_root": self.output_root,
            "records": {key: record.to_payload() for key, record in sorted(self.records.items())},
        }

    def upsert_record(
        self,
        key: str,
        *,
        source_hash: str,
        output_relpaths: list[str] | None = None,
        sink_ref: str | None = None,
    ) -> None:
        self.records[str(key)] = PipelineRecord(
            source_hash=source_hash,
            output_relpaths=list(output_relpaths or []),
            sink_ref=sink_ref,
            updated_at=utc_now_iso(),
        )


LegacyMigrator = Callable[[Path, Path, Path | None, logging.Logger], PipelineManifest | None]


class PipelineStateStore:
    def __init__(
        self,
        *,
        stage: str,
        input_root: Path,
        output_root: Path | None,
        state_root: Path,
        legacy_migrator: LegacyMigrator | None = None,
        legacy_filenames: tuple[str, ...] = (),
        log: logging.Logger | None = None,
    ) -> None:
        self.stage = stage
        self.input_root = input_root
        self.output_root = output_root
        self.state_root = state_root
        self.state_dir = state_root / SYNC_STATE_DIRNAME
        self.legacy_dir = state_root / LEGACY_CACHE_DIRNAME
        self.manifest_path = self.state_dir / MANIFEST_FILENAME
        self.lock_path = self.state_dir / LOCK_FILENAME
        self._legacy_migrator = legacy_migrator
        self._legacy_filenames = legacy_filenames
        self._log = log or logger

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        self.ensure_layout()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def ensure_layout(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        had_both_layouts = self.legacy_dir.exists() and self.state_dir.exists()
        if had_both_layouts:
            self._log.warning(
                "pipeline state | both legacy and preferred layouts exist; keeping preferred | stage=%s legacy=%s preferred=%s",
                self.stage,
                self.legacy_dir,
                self.state_dir,
            )
        elif self.legacy_dir.exists() and not self.state_dir.exists():
            self.legacy_dir.rename(self.state_dir)

        self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            return
        if had_both_layouts:
            return

        migrated = self._migrate_legacy_manifest()
        if migrated is not None:
            self.save(migrated)
            self._cleanup_legacy_files()

    def load(self) -> PipelineManifest:
        self.ensure_layout()
        if not self.manifest_path.exists():
            return self.empty_manifest()
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            self._log.warning("pipeline state | failed to read manifest, resetting | path=%s", self.manifest_path)
            return self.empty_manifest()
        return PipelineManifest.from_payload(
            payload,
            stage=self.stage,
            input_root=self.input_root,
            output_root=self.output_root,
        )

    def save(self, manifest: PipelineManifest) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.manifest_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(manifest.to_payload(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp_path, self.manifest_path)

    def empty_manifest(self) -> PipelineManifest:
        return PipelineManifest.empty(stage=self.stage, input_root=self.input_root, output_root=self.output_root)

    def _migrate_legacy_manifest(self) -> PipelineManifest | None:
        if self._legacy_migrator is None:
            return None
        if not any((self.state_dir / filename).exists() for filename in self._legacy_filenames):
            return None
        return self._legacy_migrator(self.state_dir, self.input_root, self.output_root, self._log)

    def _cleanup_legacy_files(self) -> None:
        for filename in self._legacy_filenames:
            path = self.state_dir / filename
            if path.exists():
                path.unlink()


def migrate_cleaned_dir(path: Path, *, log: logging.Logger | None = None) -> Path:
    active_log = log or logger
    if path.name == "cleaned_markdown":
        legacy_path = path.with_name("claned_markdown")
        if legacy_path.exists() and path.exists():
            active_log.warning(
                "cleaned dir | both legacy and preferred directories exist; keeping preferred | legacy=%s preferred=%s",
                legacy_path,
                path,
            )
        if legacy_path.exists() and not path.exists():
            legacy_path.rename(path)
        return path

    if path.name == "claned_markdown":
        preferred_path = path.with_name("cleaned_markdown")
        if path.exists() and not preferred_path.exists():
            path.rename(preferred_path)
        elif path.exists() and preferred_path.exists():
            active_log.warning(
                "cleaned dir | both legacy and preferred directories exist; keeping preferred | legacy=%s preferred=%s",
                path,
                preferred_path,
            )
        return preferred_path

    return path


def migrate_ocr_manifest(legacy_dir: Path, input_root: Path, output_root: Path | None, log: logging.Logger) -> PipelineManifest | None:
    hashes = _read_json_dict(legacy_dir / "file_hashes.json")
    outputs = _read_json_dict(legacy_dir / "outputs.json")
    if not hashes and not outputs:
        return None

    manifest = PipelineManifest.empty(stage="ocr", input_root=input_root, output_root=output_root)
    for legacy_key in sorted(set(hashes) | set(outputs)):
        source_hash = hashes.get(legacy_key)
        if not source_hash:
            continue
        record_key = _legacy_key_to_relative(legacy_key, input_root, log)
        if record_key is None:
            continue
        rel_output = str(outputs.get(legacy_key) or Path(record_key).with_suffix(".md"))
        manifest.upsert_record(record_key, source_hash=source_hash, output_relpaths=[rel_output], sink_ref=None)
    return manifest


def migrate_cleaning_manifest(legacy_dir: Path, input_root: Path, output_root: Path | None, log: logging.Logger) -> PipelineManifest | None:
    del log
    hashes = _read_json_dict(legacy_dir / "cleaning_hashes.json")
    if not hashes:
        return None
    manifest = PipelineManifest.empty(stage="cleaning", input_root=input_root, output_root=output_root)
    for key, source_hash in sorted(hashes.items()):
        manifest.upsert_record(str(key), source_hash=source_hash, output_relpaths=[str(key)], sink_ref=None)
    return manifest


def migrate_indexing_manifest(legacy_dir: Path, input_root: Path, output_root: Path | None, log: logging.Logger) -> PipelineManifest | None:
    del output_root, log
    hashes = _read_json_or_tsv_dict(legacy_dir / "indexing_hashes.json")
    if not hashes:
        return None
    manifest = PipelineManifest.empty(stage="indexing", input_root=input_root, output_root=None)
    for key, source_hash in sorted(hashes.items()):
        manifest.upsert_record(str(key), source_hash=source_hash, output_relpaths=[], sink_ref=str(key))
    return manifest


def _read_json_dict(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(key).strip() and str(value).strip()}


def _read_json_or_tsv_dict(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return _read_json_dict(path)

    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, sep, value = line.partition("\t")
        if not sep:
            continue
        if key.strip() and value.strip():
            result[key.strip()] = value.strip()
    return result


def _legacy_key_to_relative(raw_key: str, input_root: Path, log: logging.Logger) -> str | None:
    path = Path(str(raw_key))
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(input_root))
    except ValueError:
        log.warning("pipeline state | skipping legacy entry outside input root | key=%s input_root=%s", raw_key, input_root)
        return None
