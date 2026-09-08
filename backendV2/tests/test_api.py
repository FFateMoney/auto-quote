from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backendV2.core.api import create_app
from backendV2.core.catalog.management import CatalogDevice, CatalogDeviceDraft, CatalogTestProject, CatalogTestProjectDraft
from backendV2.core.history.repository import HistoricalQuotation
from backendV2.core.quoting.repository import DeviceCandidate, SpecificationOption
from backendV2.core.quoting.service import QuotationResult
from backendV2.core.runs.agent_runner import AgentExecution
from backendV2.core.runs.service import RunService
from backendV2.core.settings import Settings


class SuccessfulAgentRunner:
    def run(self, run_dir: Path, prompt_path: Path) -> AgentExecution:
        if not prompt_path.exists():
            raise AssertionError("missing prompt")
        (run_dir / "submit_result.json").write_text(
            json.dumps({"accepted": True, "phase": "format", "message": "成功", "details": []}),
            encoding="utf-8",
        )
        return AgentExecution(return_code=0)


class StaticQuotationProcessor:
    def quote_batch(self, quote_tables: list[object]) -> list[QuotationResult]:
        return []

    def quote_values(
        self,
        quote_id: str,
        test_project_id: int | None,
        fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        selected_device_code: str | None = None,
    ) -> QuotationResult:
        del special_fields
        selected = selected_device_code or "F10"
        return QuotationResult(
            quote_id=quote_id,
            test_project_id=test_project_id,
            eligible_device_codes=("F10", "F11"),
            selected_device_code=selected,
            base_fee=800,
            unit_price=200,
            pricing_quantity=fixed_fields.get("pricing_quantity"),
            amount=3800,
            pricing_mode="时长",
            specification="3吨台",
            standard_type="振动",
            test_item="随机振动",
            specification_options=(
                SpecificationOption(23, "3吨台", "时长"),
                SpecificationOption(24, "5吨台", "时长"),
            ),
            eligible_devices=(
                DeviceCandidate("F10", 21, {"frequency_max_hz": 2000}),
                DeviceCandidate("F11", 30, {"frequency_max_hz": 2500}),
            ),
        )


class RecordingHistoryWriter:
    def __init__(self) -> None:
        self.saved_quotations: list[HistoricalQuotation] = []

    def save_historical_quotations(self, quotations: list[HistoricalQuotation]) -> int:
        self.saved_quotations = list(quotations)
        return len(quotations)


class StaticCatalogReader:
    def __init__(self) -> None:
        self._projects = {
            23: CatalogTestProject(
                id=23,
                standard_type="振动",
                test_item="振动",
                max_specification="3吨台",
                pricing_mode="时长",
                base_fee=Decimal("1000"),
                unit_price=Decimal("300"),
                applicable_device_codes=("F1f", "F6"),
            )
        }
        self._deleted_ids: set[int] = set()
        self._next_project_id = 24
        self._devices = {
            6: CatalogDevice(
                id=6,
                device_code="F6",
                capabilities={
                    "max_load_kg": 500,
                    "frequency_min_hz": 5,
                    "frequency_max_hz": 2600,
                    "power_kwh": 37.08,
                },
            )
        }
        self._deleted_device_ids: set[int] = set()
        self._next_device_id = 7

    def list_catalog_test_projects(self) -> list[CatalogTestProject]:
        return [project for project_id, project in self._projects.items() if project_id not in self._deleted_ids]

    def list_deleted_catalog_test_projects(self) -> list[CatalogTestProject]:
        return [project for project_id, project in self._projects.items() if project_id in self._deleted_ids]

    def create_catalog_test_project(self, draft: CatalogTestProjectDraft) -> CatalogTestProject:
        project = self._project_from_draft(self._next_project_id, draft)
        self._projects[project.id] = project
        self._next_project_id += 1
        return project

    def update_catalog_test_project(self, test_project_id: int, draft: CatalogTestProjectDraft) -> CatalogTestProject:
        if test_project_id not in self._projects or test_project_id in self._deleted_ids:
            raise KeyError(test_project_id)
        project = self._project_from_draft(test_project_id, draft)
        self._projects[test_project_id] = project
        return project

    def update_catalog_test_project_aliases(
        self,
        test_project_id: int,
        aliases: tuple[str, ...],
    ) -> CatalogTestProject:
        if test_project_id not in self._projects or test_project_id in self._deleted_ids:
            raise KeyError(test_project_id)
        project = self._projects[test_project_id]
        updated = CatalogTestProject(
            id=project.id,
            standard_type=project.standard_type,
            test_item=project.test_item,
            max_specification=project.max_specification,
            pricing_mode=project.pricing_mode,
            base_fee=project.base_fee,
            unit_price=project.unit_price,
            applicable_device_codes=project.applicable_device_codes,
            aliases=aliases,
        )
        self._projects[test_project_id] = updated
        return updated

    def soft_delete_catalog_test_project(self, test_project_id: int) -> None:
        if test_project_id not in self._projects or test_project_id in self._deleted_ids:
            raise KeyError(test_project_id)
        self._deleted_ids.add(test_project_id)

    def restore_catalog_test_project(self, test_project_id: int) -> None:
        if test_project_id not in self._deleted_ids:
            raise KeyError(test_project_id)
        self._deleted_ids.remove(test_project_id)

    def list_catalog_devices(self) -> list[CatalogDevice]:
        return [device for device_id, device in self._devices.items() if device_id not in self._deleted_device_ids]

    def list_deleted_catalog_devices(self) -> list[CatalogDevice]:
        return [device for device_id, device in self._devices.items() if device_id in self._deleted_device_ids]

    def create_catalog_device(self, draft: CatalogDeviceDraft) -> CatalogDevice:
        device = CatalogDevice(self._next_device_id, draft.device_code, draft.capabilities)
        self._devices[device.id] = device
        self._next_device_id += 1
        return device

    def update_catalog_device(self, device_id: int, draft: CatalogDeviceDraft) -> CatalogDevice:
        if device_id not in self._devices or device_id in self._deleted_device_ids:
            raise KeyError(device_id)
        device = CatalogDevice(device_id, draft.device_code, draft.capabilities)
        self._devices[device_id] = device
        return device

    def soft_delete_catalog_device(self, device_id: int) -> None:
        if device_id not in self._devices or device_id in self._deleted_device_ids:
            raise KeyError(device_id)
        self._deleted_device_ids.add(device_id)

    def restore_catalog_device(self, device_id: int) -> None:
        if device_id not in self._deleted_device_ids:
            raise KeyError(device_id)
        self._deleted_device_ids.remove(device_id)

    @staticmethod
    def _project_from_draft(test_project_id: int, draft: CatalogTestProjectDraft) -> CatalogTestProject:
        return CatalogTestProject(
            id=test_project_id,
            standard_type=draft.standard_type,
            test_item=draft.test_item,
            max_specification=draft.max_specification,
            pricing_mode=draft.pricing_mode,
            base_fee=draft.base_fee,
            unit_price=draft.unit_price,
            applicable_device_codes=draft.applicable_device_codes,
        )


class RunApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            project_root=root,
            core_runtime_root=root / "core" / "runtime",
            agent_workspace_root=root / "agent_workspace",
            agent_executable="codex",
            agent_profile="quote-agent",
            qwen_api_key="",
            database={},
        )
        self.settings.agent_prompts_root.mkdir(parents=True)
        (self.settings.agent_prompts_root / "extract_quote.md").write_text("test prompt", encoding="utf-8")
        self.history_writer = RecordingHistoryWriter()
        self.service = RunService(
            self.settings,
            SuccessfulAgentRunner(),
            StaticQuotationProcessor(),
            history_writer=self.history_writer,
        )
        self.catalog = StaticCatalogReader()
        self.client = TestClient(create_app(self.settings, self.service, self.catalog))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_upload_creates_an_agent_run(self) -> None:
        response = self.client.post(
            "/api/runs",
            files=[
                ("files", ("客户报价.xlsx", b"placeholder Excel bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("files", ("参考标准.pdf", b"pdf", "application/pdf")),
            ],
        )

        self.assertEqual(response.status_code, 202)
        run_id = response.json()["run_id"]
        status = self.client.get(f"/api/runs/{run_id}")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "submitted")
        self.assertTrue((self.settings.agent_runs_root / run_id / "input" / "客户报价.xlsx").is_file())
        self.assertTrue((self.settings.agent_runs_root / run_id / "input" / "参考标准.pdf").is_file())

    def test_catalog_endpoints_return_test_projects_and_device_capabilities(self) -> None:
        projects = self.client.get("/api/catalog/test-projects")
        devices = self.client.get("/api/catalog/devices")

        self.assertEqual(projects.status_code, 200)
        self.assertEqual(
            projects.json()["items"],
            [
                {
                    "id": 23,
                    "standard_type": "振动",
                    "test_item": "振动",
                    "max_specification": "3吨台",
                    "pricing_mode": "时长",
                    "base_fee": 1000.0,
                    "unit_price": 300.0,
                    "applicable_device_codes": ["F1f", "F6"],
                    "aliases": [],
                }
            ],
        )
        self.assertEqual(devices.status_code, 200)
        self.assertIn("frequency_max_hz", devices.json()["capability_fields"])
        self.assertEqual(devices.json()["items"][0]["device_code"], "F6")
        self.assertEqual(devices.json()["items"][0]["capabilities"]["frequency_max_hz"], 2600)

    def test_catalog_test_projects_can_be_created_updated_deleted_and_restored(self) -> None:
        payload = {
            "standard_type": "振动",
            "test_item": "随机振动",
            "max_specification": "5吨台",
            "pricing_mode": "时长",
            "base_fee": 1200,
            "unit_price": 500,
            "applicable_device_codes": ["F6"],
        }
        created = self.client.post("/api/catalog/test-projects", json=payload)

        self.assertEqual(created.status_code, 201)
        created_id = created.json()["item"]["id"]
        self.assertEqual(created.json()["item"]["applicable_device_codes"], ["F6"])

        payload["unit_price"] = 600
        updated = self.client.put(f"/api/catalog/test-projects/{created_id}", json=payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["unit_price"], 600.0)

        deleted = self.client.delete(f"/api/catalog/test-projects/{created_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/catalog/test-projects/deleted").json()["items"][0]["id"], created_id)

        restored = self.client.post(f"/api/catalog/test-projects/{created_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(restored.json()["restored"])
        self.assertIn(created_id, [item["id"] for item in self.client.get("/api/catalog/test-projects").json()["items"]])

    def test_catalog_test_project_aliases_can_be_updated(self) -> None:
        response = self.client.put(
            "/api/catalog/test-projects/23/aliases",
            json={"aliases": ["随机振动", "Vibration Test"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["aliases"], ["随机振动", "Vibration Test"])
        listed = self.client.get("/api/catalog/test-projects")
        self.assertEqual(listed.json()["items"][0]["aliases"], ["随机振动", "Vibration Test"])

    def test_catalog_devices_can_be_created_updated_deleted_and_restored(self) -> None:
        payload = {
            "device_code": "T1",
            "capabilities": {"max_load_kg": 100, "frequency_max_hz": 2000},
        }
        created = self.client.post("/api/catalog/devices", json=payload)

        self.assertEqual(created.status_code, 201)
        device_id = created.json()["item"]["id"]

        payload["capabilities"]["max_load_kg"] = 120
        updated = self.client.put(f"/api/catalog/devices/{device_id}", json=payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["capabilities"]["max_load_kg"], 120)

        deleted = self.client.delete(f"/api/catalog/devices/{device_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/catalog/devices/deleted").json()["items"][0]["id"], device_id)

        restored = self.client.post(f"/api/catalog/devices/{device_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(restored.json()["restored"])
        self.assertIn(device_id, [item["id"] for item in self.client.get("/api/catalog/devices").json()["items"]])

    def test_upload_rejects_an_empty_requirement_file(self) -> None:
        response = self.client.post("/api/runs", files={"files": ("报价.pdf", b"", "application/pdf")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "empty_file")

    def test_source_file_downloads_the_primary_uploaded_file(self) -> None:
        response = self.client.post(
            "/api/runs",
            files=[
                ("files", ("客户报价.xlsx", b"primary workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("files", ("参考标准.pdf", b"reference document", "application/pdf")),
            ],
        )
        run_id = response.json()["run_id"]

        download = self.client.get(f"/api/runs/{run_id}/source-file")

        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"primary workbook")
        self.assertIn("filename*=utf-8''", download.headers["content-disposition"])

    def test_quotation_results_combine_submitted_fields_and_prices(self) -> None:
        created = self.client.post(
            "/api/runs",
            files={"files": ("报价.pdf", b"requirement", "application/pdf")},
        ).json()
        run_dir = self.settings.agent_runs_root / created["run_id"]
        quote_dir = run_dir / "quotes" / "quote-001"
        quote_dir.mkdir(parents=True)
        (quote_dir / "quote_table.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "test_project_id": 23,
                    "values": {
                        "固定字段": {"raw_test_type": "振动", "pricing_mode": "时长", "pricing_quantity": 15},
                        "专有字段": {"frequency_min_hz": 10, "frequency_max_hz": None},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (run_dir / "quotation_results.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "quote_id": "quote-001",
                            "test_project_id": 23,
                            "unit_price": 200.0,
                            "pricing_quantity": 15,
                            "amount": 3800.0,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get(f"/api/runs/{created['run_id']}/quotation-results")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {
                        "quote_id": "quote-001",
                        "test_project_id": 23,
                        "fixed_fields": {
                            "raw_test_type": "振动",
                            "standard_type": "振动",
                            "test_item": "随机振动",
                            "pricing_mode": "时长",
                            "pricing_quantity": 15,
                            "specification": "3吨台",
                        },
                        "special_fields": {"frequency_min_hz": 10, "frequency_max_hz": None},
                        "base_fee": 800.0,
                        "unit_price": 200.0,
                        "pricing_mode": "时长",
                        "pricing_quantity": 15,
                        "total_price": 3800.0,
                        "selected_device_code": "F10",
                        "eligible_devices": [
                            {"device_code": "F10", "power_kwh": 21.0, "capabilities": {"frequency_max_hz": 2000}},
                            {"device_code": "F11", "power_kwh": 30.0, "capabilities": {"frequency_max_hz": 2500}},
                        ],
                        "specification_options": [
                            {"test_project_id": 23, "specification": "3吨台", "pricing_mode": "时长"},
                            {"test_project_id": 24, "specification": "5吨台", "pricing_mode": "时长"},
                        ],
                    }
                ]
            },
        )
        history_response = self.client.post(f"/api/runs/{created['run_id']}/history-quotations")

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json(), {"saved_count": 1})
        self.assertEqual(self.history_writer.saved_quotations[0].quotation_run_id, created["run_id"])
        self.assertEqual(self.history_writer.saved_quotations[0].raw_test_type, "振动")

    def test_recalculate_quotation_returns_selected_device(self) -> None:
        created = self.client.post(
            "/api/runs",
            files={"files": ("报价.pdf", b"requirement", "application/pdf")},
        ).json()
        quote_dir = self.settings.agent_runs_root / created["run_id"] / "quotes" / "quote-001"
        quote_dir.mkdir(parents=True)
        (quote_dir / "quote_table.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "test_project_id": 23,
                    "values": {
                        "固定字段": {"raw_test_type": "振动", "pricing_quantity": 15},
                        "专有字段": {"frequency_min_hz": 10},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.post(
            f"/api/runs/{created['run_id']}/quotations/quote-001/recalculate",
            json={
                "test_project_id": 23,
                "fixed_fields": {"raw_test_type": "振动", "pricing_quantity": 15},
                "special_fields": {"frequency_min_hz": 10},
                "selected_device_code": "F11",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_device_code"], "F11")

    def test_base_fee_override_endpoint_can_be_enabled_and_restored(self) -> None:
        created = self.client.post(
            "/api/runs",
            files={"files": ("报价.pdf", b"requirement", "application/pdf")},
        ).json()
        quote_dir = self.settings.agent_runs_root / created["run_id"] / "quotes" / "quote-001"
        quote_dir.mkdir(parents=True)
        (quote_dir / "quote_table.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "test_project_id": 23,
                    "values": {
                        "固定字段": {"raw_test_type": "振动", "pricing_quantity": 15},
                        "专有字段": {"frequency_min_hz": 10},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.settings.agent_runs_root / created["run_id"] / "quotation_results.json").write_text(
            json.dumps({"items": [{"quote_id": "quote-001"}]}, ensure_ascii=False),
            encoding="utf-8",
        )

        response = self.client.post(
            f"/api/runs/{created['run_id']}/quotations/base-fee-override",
            json={"enabled": True},
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["base_fee"], 0.0)
        self.assertEqual(item["base_fee_override"], 0.0)
        self.assertEqual(item["total_price"], 3000.0)

        restored = self.client.post(
            f"/api/runs/{created['run_id']}/quotations/base-fee-override",
            json={"enabled": False},
        )

        self.assertEqual(restored.status_code, 200)
        restored_item = restored.json()["items"][0]
        self.assertEqual(restored_item["base_fee"], 800.0)
        self.assertNotIn("base_fee_override", restored_item)
        self.assertEqual(restored_item["total_price"], 3800.0)


if __name__ == "__main__":
    unittest.main()
