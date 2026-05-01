import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";

import type {
  EquipmentProfile,
  EquipmentRejection,
  ExtraStandardRequirement,
  FormRow,
  FormStageSnapshot,
  RunState,
  TestTypeCatalogResponse,
  TestTypeOption,
  UploadedDocument,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const REQUEST_TIMEOUT_MS = 20_000;
const RUN_REQUEST_TIMEOUT_MS = 10 * 60_000;

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return `${fallback}：请求等待超时，后端可能仍在处理中。`;
  }
  if (error instanceof Error && error.message) {
    return `${fallback}：${error.message}`;
  }
  return fallback;
}

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

type PreviewKind = "image" | "pdf";

type PreviewDocument = {
  fileName: string;
  kind: PreviewKind;
  url: string;
};

function getFileExtension(fileName: string): string {
  const parts = fileName.toLowerCase().split(".");
  return parts.length > 1 ? parts.at(-1) ?? "" : "";
}

function isImageDocument(document: UploadedDocument): boolean {
  if (document.media_type.toLowerCase().startsWith("image/")) {
    return true;
  }
  return ["png", "jpg", "jpeg", "bmp", "webp", "gif"].includes(getFileExtension(document.file_name));
}

function isPdfDocument(document: UploadedDocument): boolean {
  return document.media_type.toLowerCase() === "application/pdf" || getFileExtension(document.file_name) === "pdf";
}

function getDocumentAction(document: UploadedDocument): PreviewKind | "download" {
  if (isImageDocument(document)) {
    return "image";
  }
  if (isPdfDocument(document)) {
    return "pdf";
  }
  return "download";
}

function buildArtifactUrl(runId: string, storedPath: string): string {
  const encodedPath = storedPath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `${API_BASE}/runs/${encodeURIComponent(runId)}/artifacts/${encodedPath}`;
}

function triggerDownload(url: string, fileName: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

type RangeInputKey =
  | "required_temp_range"
  | "required_humidity_range"
  | "required_freq_range"
  | "required_accel_range"
  | "required_displacement_range"
  | "required_irradiance_range"
  | "required_water_temp_range"
  | "required_water_flow_range";

type DisplayFieldKey = keyof FormRow | RangeInputKey;

type ColumnDef = { key: DisplayFieldKey; label: string };

const BASE_COLUMN_DEFS: ColumnDef[] = [
  { key: "canonical_test_type", label: "标准试验类型" },
  { key: "standard_codes", label: "标准号" },
  { key: "pricing_mode", label: "计价单位" },
  { key: "pricing_quantity", label: "计价数量" },
  { key: "sample_count", label: "样品件数" },
  { key: "repeat_count", label: "重复次数" },
  { key: "sample_length_mm", label: "样品长(mm)" },
  { key: "sample_width_mm", label: "样品宽(mm)" },
  { key: "sample_height_mm", label: "样品高(mm)" },
  { key: "sample_weight_kg", label: "样品重量(kg)" },
  { key: "extra_standard_requirements", label: "额外标准要求" },
  { key: "selected_equipment_id", label: "选中设备" },
  { key: "candidate_equipment_ids", label: "候选设备" },
  { key: "base_fee", label: "基本金" },
  { key: "unit_price", label: "单价" },
  { key: "formula", label: "公式" },
  { key: "total_price", label: "总价" },
  { key: "stage_status", label: "状态" },
];

type EditableFieldKey =
  | "canonical_test_type"
  | "pricing_quantity"
  | "sample_count"
  | "repeat_count"
  | "sample_length_mm"
  | "sample_width_mm"
  | "sample_height_mm"
  | "sample_weight_kg"
  | "required_temp_change_rate"
  | RangeInputKey;

const EDITABLE_FIELD_DEFS: Record<EditableFieldKey, { label: string; inputMode: "text" | "decimal" }> = {
  canonical_test_type: { label: "标准试验类型", inputMode: "text" },
  pricing_quantity: { label: "计价数量", inputMode: "decimal" },
  sample_count: { label: "样品件数", inputMode: "decimal" },
  repeat_count: { label: "重复次数", inputMode: "decimal" },
  sample_length_mm: { label: "样品长(mm)", inputMode: "decimal" },
  sample_width_mm: { label: "样品宽(mm)", inputMode: "decimal" },
  sample_height_mm: { label: "样品高(mm)", inputMode: "decimal" },
  sample_weight_kg: { label: "样品重量(kg)", inputMode: "decimal" },
  required_temp_range: { label: "温度要求", inputMode: "text" },
  required_humidity_range: { label: "湿度要求", inputMode: "text" },
  required_temp_change_rate: { label: "温变速率", inputMode: "decimal" },
  required_freq_range: { label: "频率要求", inputMode: "text" },
  required_accel_range: { label: "加速度要求", inputMode: "text" },
  required_displacement_range: { label: "位移要求", inputMode: "text" },
  required_irradiance_range: { label: "辐照要求", inputMode: "text" },
  required_water_temp_range: { label: "水温要求", inputMode: "text" },
  required_water_flow_range: { label: "水流量要求", inputMode: "text" },
};

const MANUAL_LABELS: Record<string, string> = {
  canonical_test_type: "标准试验类型",
  pricing_quantity: "计价数量",
  sample_count: "样品件数",
  repeat_count: "重复次数",
  sample_length_mm: "样品长(mm)",
  sample_width_mm: "样品宽(mm)",
  sample_height_mm: "样品高(mm)",
  required_temp_min: "最低温度",
  required_temp_max: "最高温度",
  required_humidity_min: "最低湿度",
  required_humidity_max: "最高湿度",
  required_temp_change_rate: "温变速率",
  required_freq_min: "最低频率",
  required_freq_max: "最高频率",
  required_accel_min: "最低加速度",
  required_accel_max: "最高加速度",
  required_displacement_min: "最小位移",
  required_displacement_max: "最大位移",
  required_irradiance_min: "最低辐照",
  required_irradiance_max: "最高辐照",
  required_water_temp_min: "最低水温",
  required_water_temp_max: "最高水温",
  required_water_flow_min: "最小流量",
  required_water_flow_max: "最大流量",
  sample_weight_kg: "样品重量",
};

const RANGE_INPUT_GROUPS: Array<{
  inputKey: RangeInputKey;
  minField: keyof FormRow;
  maxField: keyof FormRow;
  label: string;
  placeholder: string;
}> = [
  {
    inputKey: "required_temp_range",
    minField: "required_temp_min",
    maxField: "required_temp_max",
    label: "温度要求",
    placeholder: "输入单值如 80，或范围如 -40～85",
  },
  {
    inputKey: "required_humidity_range",
    minField: "required_humidity_min",
    maxField: "required_humidity_max",
    label: "湿度要求",
    placeholder: "输入单值如 95，或范围如 85～95",
  },
  {
    inputKey: "required_freq_range",
    minField: "required_freq_min",
    maxField: "required_freq_max",
    label: "频率要求",
    placeholder: "输入单值如 30，或范围如 10～2000",
  },
  {
    inputKey: "required_accel_range",
    minField: "required_accel_min",
    maxField: "required_accel_max",
    label: "加速度要求",
    placeholder: "输入单值如 5，或范围如 2～10",
  },
  {
    inputKey: "required_displacement_range",
    minField: "required_displacement_min",
    maxField: "required_displacement_max",
    label: "位移要求",
    placeholder: "输入单值如 1.5，或范围如 0.5～2",
  },
  {
    inputKey: "required_irradiance_range",
    minField: "required_irradiance_min",
    maxField: "required_irradiance_max",
    label: "辐照要求",
    placeholder: "输入单值如 800，或范围如 400～800",
  },
  {
    inputKey: "required_water_temp_range",
    minField: "required_water_temp_min",
    maxField: "required_water_temp_max",
    label: "水温要求",
    placeholder: "输入单值如 25，或范围如 20～30",
  },
  {
    inputKey: "required_water_flow_range",
    minField: "required_water_flow_min",
    maxField: "required_water_flow_max",
    label: "水流量要求",
    placeholder: "输入单值如 10，或范围如 8～12",
  },
];

const EQUIPMENT_ATTR_LABELS: Record<string, string> = {
  volume_m3: "容积(m3)",
  length_mm: "长度(mm)",
  width_mm: "宽度(mm)",
  height_mm: "高度(mm)",
  power_kwh: "功率(kWh)",
  max_load_kg: "最大载荷(kg)",
  temp_min: "最低温度",
  temp_max: "最高温度",
  humidity_min: "最低湿度",
  humidity_max: "最高湿度",
  temp_change_rate_min: "最小温变速率",
  temp_change_rate_max: "最大温变速率",
  constraints_info: "约束说明",
  status: "状态",
  freq_min: "最低频率",
  freq_max: "最高频率",
  accel_min: "最低加速度",
  accel_max: "最高加速度",
  displacement_min: "最小位移",
  displacement_max: "最大位移",
  irradiance_min: "最低辐照",
  irradiance_max: "最高辐照",
  water_temp_min: "最低水温",
  water_temp_max: "最高水温",
  water_flow_min: "最小流量",
  water_flow_max: "最大流量",
};

type RowFieldDrafts = Partial<Record<EditableFieldKey, string>>;

function isEditableField(key: DisplayFieldKey): key is EditableFieldKey {
  return key in EDITABLE_FIELD_DEFS;
}

function findRangeGroup(key: DisplayFieldKey) {
  return RANGE_INPUT_GROUPS.find((group) => group.inputKey === key);
}

function getCoveredFieldNames(key: EditableFieldKey): string[] {
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return [String(rangeGroup.minField), String(rangeGroup.maxField)];
  }
  return [String(key)];
}

function formatScalarValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value == null || value === "" ? "-" : String(value);
}

function formatRangeValue(minValue: unknown, maxValue: unknown): string {
  const minText = minValue == null || minValue === "" ? "" : String(minValue);
  const maxText = maxValue == null || maxValue === "" ? "" : String(maxValue);
  if (!minText && !maxText) {
    return "-";
  }
  if (minText && maxText) {
    return `${minText}～${maxText}`;
  }
  return minText || maxText;
}

function formatExtraRequirement(item: ExtraStandardRequirement): string {
  const name = item.requirement_name || "未命名要求";
  const body = item.requirement_text || "-";
  const source = item.source_section ? `（${item.source_section}）` : "";
  return `${name}：${body}${source}`;
}

function formatExtraRequirements(items: ExtraStandardRequirement[]): string {
  if (!items.length) {
    return "-";
  }
  return items.map((item) => formatExtraRequirement(item)).join("\n");
}

function formatStatus(row: FormRow): string {
  return row.total_price != null ? "报价成功" : "报价失败";
}

function getCommittedFieldValue(row: FormRow, key: EditableFieldKey, savedDrafts: Record<string, RowFieldDrafts>): string {
  const saved = savedDrafts[row.row_id]?.[key];
  if (saved != null) {
    return saved === "" ? "-" : saved;
  }
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return formatRangeValue(row[rangeGroup.minField], row[rangeGroup.maxField]);
  }
  return formatScalarValue(row[key]);
}

function getRawFieldString(row: FormRow, key: EditableFieldKey): string {
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    const formatted = formatRangeValue(row[rangeGroup.minField], row[rangeGroup.maxField]);
    return formatted === "-" ? "" : formatted;
  }
  const value = row[key];
  if (value == null) {
    return "";
  }
  return String(value);
}

function formatCell(row: FormRow, key: DisplayFieldKey, savedDrafts: Record<string, RowFieldDrafts>): string {
  if (isEditableField(key)) {
    return getCommittedFieldValue(row, key, savedDrafts);
  }

  if (key === "missing_fields") {
    return row.missing_fields.map((field) => MANUAL_LABELS[field] ?? field).join("、");
  }

  if (key === "extra_standard_requirements") {
    return formatExtraRequirements(row.extra_standard_requirements);
  }

  if (key === "stage_status") {
    return formatStatus(row);
  }

  return formatScalarValue(row[key]);
}

function shouldShowDynamicField(rows: FormRow[], key: EditableFieldKey): boolean {
  const coveredFields = new Set(getCoveredFieldNames(key));
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return rows.some((row) => {
      const minValue = row[rangeGroup.minField];
      const maxValue = row[rangeGroup.maxField];
      return (
        (minValue != null && minValue !== "") ||
        (maxValue != null && maxValue !== "") ||
        row.missing_fields.includes(String(rangeGroup.minField)) ||
        row.missing_fields.includes(String(rangeGroup.maxField)) ||
        row.planned_standard_fields.some((field) => coveredFields.has(field)) ||
        row.discovered_standard_fields.some((field) => coveredFields.has(field))
      );
    });
  }
  return rows.some((row) => {
    const value = row[key as keyof FormRow];
    return (
      (value != null && value !== "") ||
      row.missing_fields.includes(String(key)) ||
      row.planned_standard_fields.some((field) => coveredFields.has(field)) ||
      row.discovered_standard_fields.some((field) => coveredFields.has(field))
    );
  });
}

type TestTypePickerState = {
  rowId: string;
  currentValue: string;
} | null;

function RejectedEquipmentPanel({
  activeStage,
}: {
  activeStage?: FormStageSnapshot;
}) {
  const rowsWithRejections = useMemo(
    () => (activeStage?.items ?? []).filter((row) => row.rejected_equipment.length > 0),
    [activeStage],
  );

  if (!activeStage) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3>被筛除设备表</h3>
        <p>
          只展示当前阶段的筛除结果，不再回退到历史阶段。
          当前展示阶段：{activeStage.label}
        </p>
      </div>
      {rowsWithRejections.length > 0 ? (
        <div className="rejection-groups">
          {rowsWithRejections.map((row) => (
          <div className="rejection-group" key={row.row_id}>
            <div className="rejection-group-title">
              {row.raw_test_type || row.canonical_test_type || row.row_id}
            </div>
            <div className="table-wrap">
              <table className="rejection-table">
                <thead>
                  <tr>
                    <th>设备名</th>
                    <th>不符字段/原因</th>
                  </tr>
                </thead>
                <tbody>
                  {row.rejected_equipment.map((item: EquipmentRejection) => (
                    <tr key={`${row.row_id}-${item.equipment_id}`}>
                      <td>{item.equipment_label || item.equipment_id}</td>
                      <td>{item.reasons.join("；") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          ))}
        </div>
      ) : (
        <div className="empty-state-card">当前阶段没有被筛除设备。</div>
      )}
    </section>
  );
}

function MatchedEquipmentPanel({
  activeStage,
  runState,
  onUpdated,
}: {
  activeStage?: FormStageSnapshot;
  runState: RunState;
  onUpdated: (next: RunState) => void;
}) {
  const [submittingKey, setSubmittingKey] = useState("");
  const [error, setError] = useState("");
  const rowsWithCandidates = useMemo(
    () => (activeStage?.items ?? []).filter((row) => row.candidate_equipment_profiles.length > 0),
    [activeStage],
  );

  if (!activeStage) {
    return null;
  }

  async function selectEquipment(row: FormRow, equipmentId: string) {
    if (submittingKey !== "") {
      return;
    }
    setSubmittingKey(`${row.row_id}:${equipmentId}`);
    setError("");
    try {
      const response = await fetchWithTimeout(`${API_BASE}/runs/${runState.run_id}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ row_id: row.row_id, field_values: { selected_equipment_id: equipmentId } }),
      }, RUN_REQUEST_TIMEOUT_MS);
      if (!response.ok) {
        setError(`切换设备并重新报价失败，请检查 API 服务。HTTP ${response.status}`);
        return;
      }
      const data = (await response.json()) as RunState;
      onUpdated(data);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `无法连接后端接口 ${API_BASE}/runs/${runState.run_id}/resume`));
    } finally {
      setSubmittingKey("");
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3>匹配设备表</h3>
        <p>
          展示当前候选设备的非空属性，方便对照设备能力和后续报价依据。
          当前展示阶段：{activeStage.label}
        </p>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      {rowsWithCandidates.length > 0 ? (
        <div className="rejection-groups">
          {rowsWithCandidates.map((row) => (
          <div className="rejection-group" key={`${row.row_id}-matched`}>
            <div className="rejection-group-title">
              {row.raw_test_type || row.canonical_test_type || row.row_id}
            </div>
            <div className="table-wrap">
              <table className="rejection-table">
                <thead>
                  <tr>
                    <th>设备名</th>
                    <th>非空属性</th>
                  </tr>
                </thead>
                <tbody>
                  {row.candidate_equipment_profiles.map((item: EquipmentProfile) => (
                    <tr key={`${row.row_id}-${item.equipment_id}`}>
                      <td>
                        <div className="equipment-name-cell">
                          <span>{item.equipment_label || item.equipment_id}</span>
                          {row.selected_equipment_id === item.equipment_id ? (
                            <span className="equipment-selected-badge">当前选中</span>
                          ) : (
                            <button
                              className="field-action-button equipment-select-button"
                              type="button"
                              disabled={submittingKey !== ""}
                              onClick={() => void selectEquipment(row, item.equipment_id)}
                            >
                              {submittingKey === `${row.row_id}:${item.equipment_id}` ? "切换中..." : "选用并重新报价"}
                            </button>
                          )}
                        </div>
                      </td>
                      <td>
                        {Object.entries(item.attributes)
                          .map(([key, value]) => `${EQUIPMENT_ATTR_LABELS[key] ?? key}=${String(value)}`)
                          .join("；") || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          ))}
        </div>
      ) : (
        <div className="empty-state-card">当前阶段没有候选设备。</div>
      )}
    </section>
  );
}

function StructuredFormPanel({
  activeStage,
  runState,
  onUpdated,
}: {
  activeStage?: FormStageSnapshot;
  runState: RunState;
  onUpdated: (next: RunState) => void;
}) {
  const [savedDrafts, setSavedDrafts] = useState<Record<string, RowFieldDrafts>>({});
  const [editingValues, setEditingValues] = useState<Record<string, RowFieldDrafts>>({});
  const [editingFields, setEditingFields] = useState<Record<string, Partial<Record<EditableFieldKey, boolean>>>>({});
  const [submittingRowId, setSubmittingRowId] = useState("");
  const [error, setError] = useState("");
  const [testTypePicker, setTestTypePicker] = useState<TestTypePickerState>(null);
  const [testTypeOptions, setTestTypeOptions] = useState<TestTypeOption[]>([]);
  const [testTypeLoading, setTestTypeLoading] = useState(false);
  const [testTypeError, setTestTypeError] = useState("");
  const rows = activeStage?.items ?? [];
  const pickerRow = testTypePicker ? rows.find((row) => row.row_id === testTypePicker.rowId) : undefined;
  const dynamicColumnDefs = useMemo<ColumnDef[]>(
    () =>
      [
        "required_temp_range",
        "required_humidity_range",
        "required_temp_change_rate",
        "required_freq_range",
        "required_accel_range",
        "required_displacement_range",
        "required_irradiance_range",
        "required_water_temp_range",
        "required_water_flow_range",
      ]
        .filter((key) => shouldShowDynamicField(rows, key))
        .map((key) => ({ key, label: EDITABLE_FIELD_DEFS[key].label })),
    [rows],
  );
  const columnDefs = useMemo(() => {
    const staticPrefix = BASE_COLUMN_DEFS.slice(0, 9);
    const staticSuffix = BASE_COLUMN_DEFS.slice(9);
    return [...staticPrefix, ...dynamicColumnDefs, ...staticSuffix];
  }, [dynamicColumnDefs]);

  function setEditingValue(rowId: string, field: EditableFieldKey, value: string) {
    setEditingValues((current) => ({
      ...current,
      [rowId]: {
        ...(current[rowId] ?? {}),
        [field]: value,
      },
    }));
  }

  useEffect(() => {
    if (!testTypePicker || testTypeOptions.length > 0 || testTypeLoading) {
      return;
    }

    let cancelled = false;
    async function loadTestTypes() {
      setTestTypeLoading(true);
      setTestTypeError("");
      try {
        const response = await fetchWithTimeout(`${API_BASE}/catalog/test-types`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = (await response.json()) as TestTypeCatalogResponse;
        if (cancelled) {
          return;
        }
        setTestTypeOptions(data.items);
        if (data.load_error) {
          setTestTypeError(`目录加载告警：${data.load_error}`);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setTestTypeError(toErrorMessage(fetchError, `无法获取标准试验类型目录 ${API_BASE}/catalog/test-types`));
        }
      } finally {
        if (!cancelled) {
          setTestTypeLoading(false);
        }
      }
    }

    void loadTestTypes();
    return () => {
      cancelled = true;
    };
  }, [testTypePicker, testTypeOptions.length]);

  useEffect(() => {
    if (!testTypePicker) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setTestTypePicker(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [testTypePicker]);

  function startEditing(row: FormRow, field: EditableFieldKey) {
    if (field === "canonical_test_type") {
      setTestTypePicker({
        rowId: row.row_id,
        currentValue: savedDrafts[row.row_id]?.canonical_test_type ?? getRawFieldString(row, "canonical_test_type"),
      });
      return;
    }
    setEditingValues((current) => ({
      ...current,
      [row.row_id]: {
        ...(current[row.row_id] ?? {}),
        [field]: current[row.row_id]?.[field] ?? savedDrafts[row.row_id]?.[field] ?? getRawFieldString(row, field),
      },
    }));
    setEditingFields((current) => ({
      ...current,
      [row.row_id]: {
        ...(current[row.row_id] ?? {}),
        [field]: true,
      },
    }));
  }

  function chooseTestType(row: FormRow, selectedName: string) {
    const originalValue = getRawFieldString(row, "canonical_test_type");
    setSavedDrafts((current) => {
      const rowDraft = { ...(current[row.row_id] ?? {}) };
      if (selectedName === originalValue) {
        delete rowDraft.canonical_test_type;
      } else {
        rowDraft.canonical_test_type = selectedName;
      }
      if (Object.keys(rowDraft).length === 0) {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [row.row_id]: rowDraft };
    });
    setTestTypePicker(null);
  }

  function saveField(row: FormRow, field: EditableFieldKey) {
    const nextValue = editingValues[row.row_id]?.[field] ?? savedDrafts[row.row_id]?.[field] ?? getRawFieldString(row, field);
    const originalValue = getRawFieldString(row, field);
    setSavedDrafts((current) => {
      const rowDraft = { ...(current[row.row_id] ?? {}) };
      if (nextValue === originalValue) {
        delete rowDraft[field];
      } else {
        rowDraft[field] = nextValue;
      }
      if (Object.keys(rowDraft).length === 0) {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [row.row_id]: rowDraft };
    });
    setEditingValues((current) => {
      const rowDraft = { ...(current[row.row_id] ?? {}) };
      delete rowDraft[field];
      if (Object.keys(rowDraft).length === 0) {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [row.row_id]: rowDraft };
    });
    setEditingFields((current) => ({
      ...current,
      [row.row_id]: {
        ...(current[row.row_id] ?? {}),
        [field]: false,
      },
    }));
  }

  async function submitRowChanges(row: FormRow) {
    const rowDraft = savedDrafts[row.row_id] ?? {};
    if (Object.keys(rowDraft).length === 0) {
      setError("请先保存至少一个字段修改后再重新报价。");
      return;
    }

    setSubmittingRowId(row.row_id);
    setError("");
    try {
      const response = await fetchWithTimeout(`${API_BASE}/runs/${runState.run_id}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ row_id: row.row_id, field_values: rowDraft }),
      }, RUN_REQUEST_TIMEOUT_MS);
      if (!response.ok) {
        setError(`重新报价失败，请检查 API 服务。HTTP ${response.status}`);
        return;
      }
      const data = (await response.json()) as RunState;
      setSavedDrafts((current) => {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      });
      setEditingValues((current) => {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      });
      setEditingFields((current) => {
        const { [row.row_id]: _removed, ...rest } = current;
        return rest;
      });
      onUpdated(data);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `无法连接后端接口 ${API_BASE}/runs/${runState.run_id}/resume`));
    } finally {
      setSubmittingRowId("");
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3>结构化报价表</h3>
        <p>{activeStage?.label ?? "暂无阶段"} 的完整表格快照；指定字段可人工修正并重新报价。</p>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      {activeStage && activeStage.items.length > 0 ? (
        <div className="structured-form-grid">
          {activeStage.items.map((row) => (
            <article key={row.row_id} className={row.missing_fields.length > 0 ? "structured-row-card row-warning" : "structured-row-card"}>
              <div className="structured-row-header">
                <div className="structured-row-title">{row.raw_test_type || row.canonical_test_type || row.row_id}</div>
                <div className="structured-row-meta">row_id: {row.row_id}</div>
              </div>
              <div className="structured-fields-grid">
                {columnDefs.map((column) => (
                  <section key={`${row.row_id}-${column.key}`} className="structured-field-card">
                    <div className="structured-field-head">
                      <div className="structured-field-head-main">
                        <div className="structured-field-label">{column.label}</div>
                      </div>
                      {isEditableField(column.key) ? (
                        editingFields[row.row_id]?.[column.key] ? (
                          <button
                            className="field-action-button save"
                            type="button"
                            onClick={() => saveField(row, column.key)}
                          >
                            保存
                          </button>
                        ) : (
                          <button
                            className="field-action-button"
                            type="button"
                            onClick={() => startEditing(row, column.key)}
                          >
                            {column.key === "canonical_test_type" ? "选择" : "编辑"}
                          </button>
                        )
                      ) : null}
                    </div>
                    {isEditableField(column.key) && editingFields[row.row_id]?.[column.key] ? (
                      <div className="structured-field-editor">
                        <input
                          type={EDITABLE_FIELD_DEFS[column.key].inputMode === "decimal" ? "number" : "text"}
                          step={EDITABLE_FIELD_DEFS[column.key].inputMode === "decimal" ? "any" : undefined}
                          value={editingValues[row.row_id]?.[column.key] ?? savedDrafts[row.row_id]?.[column.key] ?? getRawFieldString(row, column.key)}
                          onChange={(event) => setEditingValue(row.row_id, column.key, event.target.value)}
                          placeholder={EDITABLE_FIELD_DEFS[column.key].label}
                        />
                      </div>
                    ) : (
                      <div
                        className="structured-field-value"
                        title={formatCell(row, column.key, savedDrafts)}
                        style={column.key === "extra_standard_requirements" ? { whiteSpace: "pre-wrap" } : undefined}
                      >
                        {formatCell(row, column.key, savedDrafts)}
                      </div>
                    )}
                    {isEditableField(column.key) && !editingFields[row.row_id]?.[column.key] && savedDrafts[row.row_id]?.[column.key] != null ? (
                      <div className="structured-field-status">
                        已保存修改
                      </div>
                    ) : null}
                  </section>
                ))}
              </div>
              {Object.keys(savedDrafts[row.row_id] ?? {}).length > 0 ? (
                <div className="structured-row-actions">
                  <div className="structured-row-actions-text">
                    已保存 {Object.keys(savedDrafts[row.row_id] ?? {}).length} 个字段修改，可直接基于当前人工修正结果重新报价。
                  </div>
                  <button
                    className="primary-button"
                    type="button"
                    disabled={submittingRowId !== "" && submittingRowId === row.row_id}
                    onClick={() => void submitRowChanges(row)}
                  >
                    {submittingRowId !== "" && submittingRowId === row.row_id ? "重新报价中..." : "按已保存修改重新报价"}
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state-card">还没有可展示的结构化表行。</div>
      )}
      {testTypePicker ? (
        <div className="preview-overlay" role="presentation" onClick={() => setTestTypePicker(null)}>
          <div
            className="picker-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="选择标准试验类型"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="preview-header">
              <div>
                <div className="preview-title">选择标准试验类型</div>
                <div className="picker-subtitle">当前值：{testTypePicker.currentValue || "未填写"}</div>
              </div>
              <div className="preview-actions">
                <button className="preview-close-button" type="button" onClick={() => setTestTypePicker(null)}>
                  关闭
                </button>
              </div>
            </div>
            <div className="picker-body">
              {testTypeLoading ? <div className="empty-state-card">正在加载标准试验类型目录...</div> : null}
              {!testTypeLoading && testTypeError ? <div className="error-banner">{testTypeError}</div> : null}
              {!testTypeLoading && testTypeOptions.length > 0 ? (
                <div className="picker-list">
                  {pickerRow
                    ? testTypeOptions.map((option) => {
                        const selectedValue =
                          savedDrafts[pickerRow.row_id]?.canonical_test_type ?? getRawFieldString(pickerRow, "canonical_test_type");
                        const isSelected = selectedValue === option.name;
                        return (
                          <button
                            key={`${pickerRow.row_id}-${option.id}`}
                            type="button"
                            className={isSelected ? "picker-option picker-option-selected" : "picker-option"}
                            onClick={() => chooseTestType(pickerRow, option.name)}
                          >
                            <span className="picker-option-name">{option.name}</span>
                            <span className="picker-option-meta">
                              计价单位：{option.pricing_mode || "-"}
                              {option.aliases.length > 0 ? ` | 别名：${option.aliases.join("、")}` : ""}
                            </span>
                          </button>
                        );
                      })
                    : null}
                </div>
              ) : null}
              {!testTypeLoading && !testTypeError && testTypeOptions.length === 0 ? (
                <div className="empty-state-card">目录里还没有可选的标准试验类型。</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function App() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [activeStageId, setActiveStageId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [previewDocument, setPreviewDocument] = useState<PreviewDocument | null>(null);

  const activeStage: FormStageSnapshot | undefined = useMemo(() => {
    if (!runState) {
      return undefined;
    }
    return (
      runState.form_stages.find((stage) => stage.stage_id === activeStageId) ??
      runState.form_stages.at(-1)
    );
  }, [activeStageId, runState]);

  useEffect(() => {
    if (!previewDocument) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPreviewDocument(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewDocument]);

  async function submitFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files || files.length === 0) {
      setError("请先选择至少一个 Word、Excel、PDF 或图片文件。");
      return;
    }
    setSubmitting(true);
    setError("");

    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    try {
      const response = await fetchWithTimeout(`${API_BASE}/runs`, {
        method: "POST",
        body: formData,
      }, RUN_REQUEST_TIMEOUT_MS);

      if (!response.ok) {
        setError(`运行创建失败，请检查后端服务。HTTP ${response.status}`);
        return;
      }

      const data = (await response.json()) as RunState;
      setRunState(data);
      setActiveStageId(data.form_stages.at(-1)?.stage_id ?? "");
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `无法连接后端接口 ${API_BASE}/runs`));
    } finally {
      setSubmitting(false);
    }
  }

  function handleUploadedDocumentClick(event: MouseEvent<HTMLAnchorElement>, document: UploadedDocument) {
    if (!runState) {
      return;
    }

    event.preventDefault();
    const url = buildArtifactUrl(runState.run_id, document.stored_path);
    const action = getDocumentAction(document);
    if (action === "download") {
      triggerDownload(url, document.file_name);
      return;
    }
    setPreviewDocument({
      fileName: document.file_name,
      kind: action,
      url,
    });
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <div className="eyebrow">Auto Quote</div>
          <h1>结构化报价表驱动的自动报价流程</h1>
          <p>同一张表，从文件抽取到最终报价，所有步骤都只是在持续补表。</p>
        </div>
        <form className="upload-card" onSubmit={submitFiles}>
          <label className="file-picker">
              <span>上传文档</span>
            <input
              type="file"
              accept=".docx,.xlsx,.pdf,.png,.jpg,.jpeg,.bmp,.webp"
              multiple
              onChange={(event) => setFiles(event.target.files)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "处理中..." : "开始填表"}
          </button>
          <div className="api-hint">当前前端接口地址：{API_BASE}</div>
          {error ? <div className="error-banner">{error}</div> : null}
        </form>
      </header>

      {runState ? (
        <>
          <section className="panel status-panel">
            <div className="panel-header">
              <h3>运行状态</h3>
              <p>{runState.next_action || "等待下一步"}</p>
            </div>
            <div className="status-grid">
              <div>
                <span className="status-label">Run ID</span>
                <strong>{runState.run_id}</strong>
              </div>
              <div>
                <span className="status-label">整体状态</span>
                <strong>{runState.overall_status}</strong>
              </div>
              <div>
                <span className="status-label">当前阶段</span>
                <strong>{runState.current_stage}</strong>
              </div>
              <div>
                <span className="status-label">上传文件</span>
                <strong className="uploaded-document-list">
                  {runState.uploaded_documents.map((item) => (
                    <a
                      key={item.document_id}
                      className="uploaded-document-link"
                      href={buildArtifactUrl(runState.run_id, item.stored_path)}
                      onClick={(event) => handleUploadedDocumentClick(event, item)}
                    >
                      {item.file_name}
                    </a>
                  ))}
                </strong>
              </div>
            </div>
            {runState.errors.length > 0 ? (
              <div className="error-banner">{runState.errors.join("；")}</div>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h3>阶段切换</h3>
              <p>表头不变，只切换这张结构化报价表在不同步骤的填写快照。</p>
            </div>
            <div className="stage-strip">
              {runState.form_stages.map((stage) => (
                <button
                  key={stage.stage_id}
                  className={stage.stage_id === activeStage?.stage_id ? "stage-pill active" : "stage-pill"}
                  type="button"
                  onClick={() => setActiveStageId(stage.stage_id)}
                >
                  {stage.label}
                </button>
              ))}
            </div>
            {activeStage ? (
              <div className="stage-notes">
                {activeStage.notes.map((note, index) => (
                  <div className="note-chip" key={`${activeStage.stage_id}-${index}`}>
                    {note}
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <StructuredFormPanel
            activeStage={activeStage}
            runState={runState}
            onUpdated={(next) => {
              setRunState(next);
              setActiveStageId(next.current_stage);
            }}
          />

          <MatchedEquipmentPanel
            activeStage={activeStage}
            runState={runState}
            onUpdated={(next) => {
              setRunState(next);
              setActiveStageId(next.current_stage);
            }}
          />
          <RejectedEquipmentPanel activeStage={activeStage} />

        </>
      ) : null}

      {previewDocument ? (
        <div className="preview-overlay" role="presentation" onClick={() => setPreviewDocument(null)}>
          <div className="preview-dialog" role="dialog" aria-modal="true" aria-label={previewDocument.fileName} onClick={(event) => event.stopPropagation()}>
            <div className="preview-header">
              <div className="preview-title">{previewDocument.fileName}</div>
              <div className="preview-actions">
                <a className="preview-link-button" href={previewDocument.url} download={previewDocument.fileName}>
                  下载
                </a>
                <button className="preview-close-button" type="button" onClick={() => setPreviewDocument(null)}>
                  关闭
                </button>
              </div>
            </div>
            <div className="preview-body">
              {previewDocument.kind === "image" ? (
                <img className="preview-image" src={previewDocument.url} alt={previewDocument.fileName} />
              ) : (
                <iframe className="preview-frame" src={previewDocument.url} title={previewDocument.fileName} />
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
