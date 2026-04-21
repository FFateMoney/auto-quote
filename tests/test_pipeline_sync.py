from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

if "bs4" not in sys.modules:
    sys.modules["bs4"] = types.SimpleNamespace(BeautifulSoup=object, Tag=object)

if "qdrant_client" not in sys.modules:
    sys.modules["qdrant_client"] = types.SimpleNamespace(
        QdrantClient=object,
        models=types.SimpleNamespace(),
    )

if "torch" not in sys.modules:
    torch_module = types.ModuleType("torch")
    torch_module.bfloat16 = object()
    torch_module.float32 = object()
    torch_module.Tensor = object
    torch_module.no_grad = lambda: (lambda fn: fn)
    torch_module.arange = lambda *args, **kwargs: []
    torch_module.cuda = types.SimpleNamespace(empty_cache=lambda: None)
    torch_nn_module = types.ModuleType("torch.nn")
    torch_nn_functional = types.ModuleType("torch.nn.functional")
    torch_nn_functional.normalize = lambda embeddings, p=2, dim=1: embeddings
    torch_module.nn = torch_nn_module
    sys.modules["torch"] = torch_module
    sys.modules["torch.nn"] = torch_nn_module
    sys.modules["torch.nn.functional"] = torch_nn_functional

if "transformers" not in sys.modules:
    transformers_module = types.ModuleType("transformers")
    transformers_module.AutoTokenizer = object
    transformers_module.AutoModel = object
    transformers_module.AutoModelForSequenceClassification = object
    sys.modules["transformers"] = transformers_module

from backend.cleaning.library import CleaningLibrary
from backend.cleaning.settings import CleaningSettings
from backend.common.pipeline_state import migrate_cleaned_dir
from backend.indexing.library import IndexingLibrary
from backend.indexing.settings import IndexingSettings
from backend.ocr.library import LibraryBuilder
from backend.ocr.settings import OcrSettings


class DummyOcrService:
    def process_path(self, path: Path) -> SimpleNamespace:
        return SimpleNamespace(markdown_text=f"# {path.stem}\n\nOCR:{path.name}")


class DummyCleaningService:
    def clean_file(self, path: Path) -> SimpleNamespace:
        return SimpleNamespace(cleaned_content=path.read_text(encoding="utf-8").upper())


class FakeStore:
    def __init__(self, *, has_points: bool) -> None:
        self._has_points = has_points
        self.deleted_keys: list[str] = []

    def has_points(self) -> bool:
        return self._has_points

    def delete_by_source_key(self, source_key: str) -> None:
        self.deleted_keys.append(source_key)


class FakeIndexingService:
    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self.index_calls: list[tuple[str, str]] = []
        self.reset_calls = 0

    def index_file(self, content: str, file_name: str, standard_id: str, source_key: str) -> int:
        self.index_calls.append((file_name, source_key))
        return max(1, len(content))

    def reset_all(self) -> None:
        self.reset_calls += 1


class PipelineSyncTests(unittest.TestCase):
    def test_migrate_cleaned_dir_renames_legacy_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            legacy_dir = data_dir / "claned_markdown"
            preferred_dir = data_dir / "cleaned_markdown"
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "demo.md").write_text("x", encoding="utf-8")

            result = migrate_cleaned_dir(preferred_dir)

            self.assertEqual(result, preferred_dir)
            self.assertTrue(preferred_dir.exists())
            self.assertFalse(legacy_dir.exists())
            self.assertTrue((preferred_dir / "demo.md").exists())

    def test_ocr_sync_removes_deleted_source_and_writes_sync_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin_dir = root / "origin"
            output_dir = root / "ocr_markdown"
            origin_dir.mkdir()
            (origin_dir / "a.pdf").write_text("alpha", encoding="utf-8")
            (origin_dir / "b.pdf").write_text("beta", encoding="utf-8")

            settings = OcrSettings(
                host="127.0.0.1",
                port=8001,
                origin_dir=origin_dir,
                output_dir=output_dir,
                device="cpu",
                text_detection_model="det",
                text_recognition_model="rec",
                use_region_detection=False,
                use_table_recognition=False,
                format_block_content=False,
                markdown_ignore_labels=[],
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                use_seal_recognition=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
                use_table_orientation_classify=False,
            )
            library = LibraryBuilder(settings)
            library._service = DummyOcrService()

            report1 = library.sync()
            self.assertEqual(report1.processed, 2)
            self.assertTrue((output_dir / "sync_state" / "sync_state.json").exists())

            (origin_dir / "b.pdf").unlink()
            report2 = library.sync()

            self.assertEqual(report2.removed, 1)
            self.assertFalse((output_dir / "b.md").exists())
            manifest = json.loads((output_dir / "sync_state" / "sync_state.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(manifest["records"]), ["a.pdf"])

    def test_cleaning_sync_removes_deleted_input_and_writes_sync_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "ocr_markdown"
            output_dir = root / "cleaned_markdown"
            input_dir.mkdir()
            (input_dir / "a.md").write_text("alpha", encoding="utf-8")
            (input_dir / "b.md").write_text("beta", encoding="utf-8")

            settings = CleaningSettings(host="127.0.0.1", port=8002, input_dir=input_dir, output_dir=output_dir)
            library = CleaningLibrary(settings)
            library._service = DummyCleaningService()

            report1 = library.sync()
            self.assertEqual(report1.processed, 2)
            self.assertTrue((output_dir / "sync_state" / "sync_state.json").exists())

            (input_dir / "b.md").unlink()
            report2 = library.sync()

            self.assertEqual(report2.skipped, 1)
            self.assertFalse((output_dir / "b.md").exists())
            manifest = json.loads((output_dir / "sync_state" / "sync_state.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(manifest["records"]), ["a.md"])

    def test_indexing_sync_migrates_tsv_and_reindexes_when_collection_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "cleaned_markdown"
            cache_dir = input_dir / ".cache"
            input_dir.mkdir()
            cache_dir.mkdir()
            content = "# Title\n\nalpha"
            file_path = input_dir / "a.md"
            file_path.write_text(content, encoding="utf-8")
            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            (cache_dir / "indexing_hashes.json").write_text(f"a.md\t{file_hash}\n", encoding="utf-8")

            settings = IndexingSettings(
                host="127.0.0.1",
                port=8003,
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                collection_name="standard_kb",
                input_dir=input_dir,
                embedding_model_path="dummy",
                reranker_model_path="dummy",
            )
            fake_store = FakeStore(has_points=False)
            fake_service = FakeIndexingService(fake_store)

            with mock.patch("backend.indexing.library.Qwen3EmbeddingEngine", return_value=object()):
                with mock.patch(
                    "backend.indexing.library.IndexingService",
                    side_effect=lambda engine=None: fake_service,
                ):
                    library = IndexingLibrary(settings)
                    report = library.sync()

            self.assertEqual(report.failed_files, 0)
            self.assertEqual(fake_service.index_calls, [("a.md", "a.md")])
            self.assertTrue((input_dir / "sync_state" / "sync_state.json").exists())
            self.assertFalse((input_dir / ".cache" / "indexing_hashes.json").exists())

    def test_indexing_sync_removes_deleted_inputs_even_when_directory_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "cleaned_markdown"
            sync_dir = input_dir / "sync_state"
            input_dir.mkdir()
            sync_dir.mkdir()
            manifest = {
                "version": 1,
                "stage": "indexing",
                "input_root": str(input_dir),
                "output_root": None,
                "records": {
                    "ghost.md": {
                        "source_hash": "deadbeef",
                        "output_relpaths": [],
                        "sink_ref": "ghost.md",
                        "updated_at": "2026-04-20T00:00:00+00:00",
                    }
                },
            }
            (sync_dir / "sync_state.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            settings = IndexingSettings(
                host="127.0.0.1",
                port=8003,
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                collection_name="standard_kb",
                input_dir=input_dir,
                embedding_model_path="dummy",
                reranker_model_path="dummy",
            )
            fake_store = FakeStore(has_points=True)
            fake_service = FakeIndexingService(fake_store)

            with mock.patch("backend.indexing.library.Qwen3EmbeddingEngine", return_value=None):
                with mock.patch(
                    "backend.indexing.library.IndexingService",
                    side_effect=lambda engine=None: fake_service,
                ):
                    library = IndexingLibrary(settings)
                    report = library.sync()

            self.assertEqual(report.total_files, 0)
            self.assertEqual(fake_store.deleted_keys, ["ghost.md"])
            updated = json.loads((sync_dir / "sync_state.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["records"], {})


if __name__ == "__main__":
    unittest.main()
