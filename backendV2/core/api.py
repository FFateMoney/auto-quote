from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backendV2.core.catalog.management import (
    DEVICE_CAPABILITY_FIELDS,
    CatalogManagementReader,
    CatalogManagementRepository,
    CatalogDeviceDraft,
    CatalogTestProjectDraft,
)
from backendV2.core.runs.service import RunInputFile, RunService
from backendV2.core.settings import Settings


class RecalculateQuotationRequest(BaseModel):
    test_project_id: int | None
    fixed_fields: dict[str, Any]
    special_fields: dict[str, Any]
    selected_device_code: str | None = None
    base_fee_override: Decimal | None = None


class BaseFeeOverrideRequest(BaseModel):
    enabled: bool


class CatalogTestProjectRequest(BaseModel):
    standard_type: str = Field(min_length=1)
    test_item: str = Field(min_length=1)
    max_specification: str = Field(min_length=1)
    pricing_mode: str = Field(min_length=1)
    base_fee: Decimal
    unit_price: Decimal
    applicable_device_codes: list[str] = Field(default_factory=list)

    def to_draft(self) -> CatalogTestProjectDraft:
        return CatalogTestProjectDraft(
            standard_type=self.standard_type,
            test_item=self.test_item,
            max_specification=self.max_specification,
            pricing_mode=self.pricing_mode,
            base_fee=self.base_fee,
            unit_price=self.unit_price,
            applicable_device_codes=tuple(self.applicable_device_codes),
        )


class CatalogDeviceRequest(BaseModel):
    device_code: str = Field(min_length=1)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    def to_draft(self) -> CatalogDeviceDraft:
        return CatalogDeviceDraft(
            device_code=self.device_code,
            capabilities=self.capabilities,
        )


class CatalogTestProjectAliasesRequest(BaseModel):
    aliases: list[str] = Field(default_factory=list)


def create_app(
    settings: Settings | None = None,
    run_service: RunService | None = None,
    catalog_reader: CatalogManagementReader | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    service = run_service or RunService(active_settings)
    catalog = catalog_reader or CatalogManagementRepository(active_settings)
    app = FastAPI(title="Agent Quote Core", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/auth/session")
    def auth_session() -> dict[str, bool]:
        return {"auth_enabled": False, "authenticated": True}

    @app.get("/api/catalog/test-projects")
    def list_catalog_test_projects() -> dict[str, object]:
        return {"items": [project.to_dict() for project in catalog.list_catalog_test_projects()]}

    @app.get("/api/catalog/test-projects/deleted")
    def list_deleted_catalog_test_projects() -> dict[str, object]:
        return {"items": [project.to_dict() for project in catalog.list_deleted_catalog_test_projects()]}

    @app.post("/api/catalog/test-projects", status_code=201)
    def create_catalog_test_project(request: CatalogTestProjectRequest) -> dict[str, object]:
        try:
            project = catalog.create_catalog_test_project(request.to_draft())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": project.to_dict()}

    @app.put("/api/catalog/test-projects/{test_project_id}/aliases")
    def update_catalog_test_project_aliases(
        test_project_id: int,
        request: CatalogTestProjectAliasesRequest,
    ) -> dict[str, object]:
        try:
            project = catalog.update_catalog_test_project_aliases(test_project_id, tuple(request.aliases))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="test_project_not_found") from exc
        return {"item": project.to_dict()}

    @app.put("/api/catalog/test-projects/{test_project_id}")
    def update_catalog_test_project(test_project_id: int, request: CatalogTestProjectRequest) -> dict[str, object]:
        try:
            project = catalog.update_catalog_test_project(test_project_id, request.to_draft())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="test_project_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": project.to_dict()}

    @app.delete("/api/catalog/test-projects/{test_project_id}", status_code=204)
    def delete_catalog_test_project(test_project_id: int) -> Response:
        try:
            catalog.soft_delete_catalog_test_project(test_project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="test_project_not_found") from exc
        return Response(status_code=204)

    @app.post("/api/catalog/test-projects/{test_project_id}/restore")
    def restore_catalog_test_project(test_project_id: int) -> dict[str, bool]:
        try:
            catalog.restore_catalog_test_project(test_project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="deleted_test_project_not_found") from exc
        return {"restored": True}

    @app.get("/api/catalog/devices")
    def list_catalog_devices() -> dict[str, object]:
        return {
            "capability_fields": list(DEVICE_CAPABILITY_FIELDS),
            "items": [device.to_dict() for device in catalog.list_catalog_devices()],
        }

    @app.get("/api/catalog/devices/deleted")
    def list_deleted_catalog_devices() -> dict[str, object]:
        return {
            "capability_fields": list(DEVICE_CAPABILITY_FIELDS),
            "items": [device.to_dict() for device in catalog.list_deleted_catalog_devices()],
        }

    @app.post("/api/catalog/devices", status_code=201)
    def create_catalog_device(request: CatalogDeviceRequest) -> dict[str, object]:
        try:
            device = catalog.create_catalog_device(request.to_draft())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": device.to_dict()}

    @app.put("/api/catalog/devices/{device_id}")
    def update_catalog_device(device_id: int, request: CatalogDeviceRequest) -> dict[str, object]:
        try:
            device = catalog.update_catalog_device(device_id, request.to_draft())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="device_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"item": device.to_dict()}

    @app.delete("/api/catalog/devices/{device_id}", status_code=204)
    def delete_catalog_device(device_id: int) -> Response:
        try:
            catalog.soft_delete_catalog_device(device_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="device_not_found") from exc
        return Response(status_code=204)

    @app.post("/api/catalog/devices/{device_id}/restore")
    def restore_catalog_device(device_id: int) -> dict[str, bool]:
        try:
            catalog.restore_catalog_device(device_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="deleted_device_not_found") from exc
        return {"restored": True}

    @app.post("/api/auth/login")
    def login() -> dict[str, object]:
        return {"authenticated": True, "expires_in": 0}

    @app.post("/api/auth/logout")
    def logout() -> dict[str, bool]:
        return {"authenticated": False}

    @app.get("/api/runs")
    def list_runs() -> dict[str, object]:
        return {
            "items": [
                {
                    "run_id": snapshot.run_id,
                    "label": snapshot.run_id,
                    "quote_mode": "",
                    "overall_status": snapshot.status,
                    "current_stage": snapshot.status,
                    "created_at": snapshot.created_at,
                    "updated_at": snapshot.updated_at,
                    "uploaded_files": [snapshot.uploaded_file],
                }
                for snapshot in service.list_runs()
            ]
        }

    @app.post("/api/runs", status_code=202)
    async def create_run(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=400, detail="missing_files")
        primary_file, *reference_files = files
        file_name = primary_file.filename or "报价需求"
        content = await primary_file.read()
        references: list[RunInputFile] = []
        for index, file in enumerate(reference_files, start=1):
            references.append(RunInputFile(file.filename or f"参考文件_{index}", await file.read()))
        try:
            snapshot = service.create_run(file_name, content, tuple(references))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(service.run_agent, snapshot.run_id)
        return snapshot.to_dict()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        try:
            return service.get_run(run_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.get("/api/runs/{run_id}/source-file")
    def download_source_file(run_id: str) -> FileResponse:
        try:
            source_file = service.get_source_file(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="source_file_not_found") from exc
        return FileResponse(source_file, filename=source_file.name)

    @app.get("/api/runs/{run_id}/quotation-results")
    def get_quotation_results(run_id: str) -> dict[str, object]:
        try:
            return service.get_quotation_results(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.post("/api/runs/{run_id}/quotations/{quote_id}/recalculate")
    def recalculate_quotation(
        run_id: str,
        quote_id: str,
        request: RecalculateQuotationRequest,
    ) -> dict[str, object]:
        try:
            return service.recalculate_quotation(
                run_id,
                quote_id,
                request.test_project_id,
                request.fixed_fields,
                request.special_fields,
                request.selected_device_code,
                request.base_fee_override,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_or_quote_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/quotations/{quote_id}/snapshot")
    def save_quotation_snapshot(
        run_id: str,
        quote_id: str,
        request: RecalculateQuotationRequest,
    ) -> dict[str, object]:
        try:
            return service.save_quotation_snapshot(
                run_id,
                quote_id,
                request.test_project_id,
                request.fixed_fields,
                request.special_fields,
                request.selected_device_code,
                request.base_fee_override,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_or_quote_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/quotations/base-fee-override")
    def set_quotation_base_fee_override(
        run_id: str,
        request: BaseFeeOverrideRequest,
    ) -> dict[str, object]:
        try:
            return service.set_all_quotation_base_fee_overrides(run_id, Decimal("0") if request.enabled else None)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/history-quotations")
    def save_current_quotations_to_history(run_id: str) -> dict[str, int]:
        try:
            saved_count = service.save_current_quotations_to_history(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        return {"saved_count": saved_count}

    @app.post("/api/runs/{run_id}/export")
    def export_quotation_document(run_id: str, quote_id: str = "") -> FileResponse:
        try:
            output = service.export_quotation_document(run_id, quote_id=quote_id.strip())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_or_quote_not_found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            if str(exc) == "no_quoted_items_to_export":
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return FileResponse(
            output,
            filename=output.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    return app
