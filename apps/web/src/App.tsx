import { FormEvent, useMemo, useState } from "react";

import type { EquipmentProfile, EquipmentRejection, FormRow, FormStageSnapshot, RunState } from "./types";

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

const COLUMN_DEFS: Array<{ key: keyof FormRow | "standard_files"; label: string }> = [
  { key: "raw_test_type", label: "原始试验类型" },
  { key: "canonical_test_type", label: "标准试验类型" },
  { key: "standard_codes", label: "标准号" },
  { key: "pricing_mode", label: "计价单位" },
  { key: "pricing_quantity", label: "计价数量" },
  { key: "repeat_count", label: "重复次数" },
  { key: "sample_length_mm", label: "样品长(mm)" },
  { key: "sample_width_mm", label: "样品宽(mm)" },
  { key: "sample_height_mm", label: "样品高(mm)" },
  { key: "sample_weight_kg", label: "样品重量(kg)" },
  { key: "conditions_text", label: "条件摘要" },
  { key: "sample_info_text", label: "样品摘要" },
  { key: "standard_files", label: "标准文件" },
  { key: "matched_test_type_id", label: "试验类型ID" },
  { key: "selected_equipment_id", label: "选中设备" },
  { key: "candidate_equipment_ids", label: "候选设备" },
  { key: "base_fee", label: "基本金" },
  { key: "unit_price", label: "单价" },
  { key: "total_price", label: "总价" },
  { key: "formula", label: "公式" },
  { key: "stage_status", label: "行状态" },
  { key: "blocking_reason", label: "阻塞原因" },
  { key: "source_text", label: "来源摘要" },
];

const MANUAL_LABELS: Record<string, string> = {
  canonical_test_type: "标准试验类型",
  pricing_quantity: "计价数量",
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

const RANGE_INPUT_GROUPS = [
  {
    inputKey: "required_temp_range",
    minField: "required_temp_min",
    maxField: "required_temp_max",
    label: "温度要求",
    placeholder: "输入单值如 80，或范围如 -40~85",
  },
  {
    inputKey: "required_humidity_range",
    minField: "required_humidity_min",
    maxField: "required_humidity_max",
    label: "湿度要求",
    placeholder: "输入单值如 95，或范围如 85~95",
  },
  {
    inputKey: "required_freq_range",
    minField: "required_freq_min",
    maxField: "required_freq_max",
    label: "频率要求",
    placeholder: "输入单值如 30，或范围如 10~2000",
  },
  {
    inputKey: "required_accel_range",
    minField: "required_accel_min",
    maxField: "required_accel_max",
    label: "加速度要求",
    placeholder: "输入单值如 5，或范围如 2~10",
  },
  {
    inputKey: "required_displacement_range",
    minField: "required_displacement_min",
    maxField: "required_displacement_max",
    label: "位移要求",
    placeholder: "输入单值如 1.5，或范围如 0.5~2",
  },
  {
    inputKey: "required_irradiance_range",
    minField: "required_irradiance_min",
    maxField: "required_irradiance_max",
    label: "辐照要求",
    placeholder: "输入单值如 800，或范围如 400~800",
  },
  {
    inputKey: "required_water_temp_range",
    minField: "required_water_temp_min",
    maxField: "required_water_temp_max",
    label: "水温要求",
    placeholder: "输入单值如 25，或范围如 20~30",
  },
  {
    inputKey: "required_water_flow_range",
    minField: "required_water_flow_min",
    maxField: "required_water_flow_max",
    label: "水流量要求",
    placeholder: "输入单值如 10，或范围如 8~12",
  },
] as const;

type ManualFieldSpec = {
  inputKey: string;
  label: string;
  placeholder: string;
};

function buildManualFieldSpecs(row: FormRow): ManualFieldSpec[] {
  const missing = new Set(row.missing_fields);
  const consumed = new Set<string>();
  const specs: ManualFieldSpec[] = [];

  for (const group of RANGE_INPUT_GROUPS) {
    const minMissing = missing.has(group.minField);
    const maxMissing = missing.has(group.maxField);
    const minValue = row[group.minField as keyof FormRow];
    const maxValue = row[group.maxField as keyof FormRow];
    if (minMissing && maxMissing && (minValue == null || minValue === "") && (maxValue == null || maxValue === "")) {
      specs.push({
        inputKey: group.inputKey,
        label: group.label,
        placeholder: group.placeholder,
      });
      consumed.add(group.minField);
      consumed.add(group.maxField);
    }
  }

  for (const fieldName of row.missing_fields) {
    if (consumed.has(fieldName)) {
      continue;
    }
    specs.push({
      inputKey: fieldName,
      label: MANUAL_LABELS[fieldName] ?? fieldName,
      placeholder: `填写 ${MANUAL_LABELS[fieldName] ?? fieldName}`,
    });
  }

  return specs;
}

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

function formatCell(row: FormRow, key: keyof FormRow | "standard_files"): string {
  if (key === "standard_files") {
    return row.source_refs
      .filter((item) => item.kind === "standard_file")
      .map((item) => item.label || item.path.split("/").at(-1) || item.path)
      .join(", ");
  }

  if (key === "blocking_reason") {
    const value = row[key];
    return value == null || value === "" ? "-" : String(value);
  }

  if (key === "missing_fields") {
    return row.missing_fields.map((field) => MANUAL_LABELS[field] ?? field).join("、");
  }

  const value = row[key];
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value == null || value === "" ? "-" : String(value);
}

function ManualEditor({
  runState,
  onUpdated,
}: {
  runState: RunState;
  onUpdated: (next: RunState) => void;
}) {
  const targetRows = useMemo(
    () => runState.final_form_items.filter((row) => row.missing_fields.length > 0),
    [runState],
  );
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [submittingRowId, setSubmittingRowId] = useState("");
  const [error, setError] = useState("");

  if (targetRows.length === 0) {
    return null;
  }

  async function submitRow(row: FormRow) {
    const values = drafts[row.row_id] ?? {};
    const fieldValues = Object.fromEntries(
      Object.entries(values)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value !== ""),
    );

    if (Object.keys(fieldValues).length === 0) {
      setError("至少填写一个缺失字段后再继续报价。");
      return;
    }

    setSubmittingRowId(row.row_id);
    setError("");
    try {
      const response = await fetchWithTimeout(`${API_BASE}/runs/${runState.run_id}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ row_id: row.row_id, field_values: fieldValues }),
      }, RUN_REQUEST_TIMEOUT_MS);
      if (!response.ok) {
        setError(`继续报价失败，请检查 API 服务。HTTP ${response.status}`);
        return;
      }
      const data = (await response.json()) as RunState;
      setDrafts({});
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
        <h3>人工补录</h3>
        <p>补齐当前缺失信息后，每点击一次都会重新尝试筛选设备并报价；即使当前已有报价，也可以继续补充字段扩大可用设备范围。</p>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="manual-grid">
        {targetRows.map((row) => {
          const manualFields = buildManualFieldSpecs(row);
          return (
            <article className="manual-card" key={row.row_id}>
              <div className="manual-card-title">
                {row.raw_test_type || row.canonical_test_type || row.row_id}
              </div>
              <div className="manual-card-subtitle">
                {row.blocking_reason || "部分设备因字段缺失被筛除，可补充后重新尝试报价"}
              </div>
              <div className="manual-fields">
                {manualFields.map((field) => (
                  <label className="manual-field" key={field.inputKey}>
                    <span>{field.label}</span>
                    <input
                      value={drafts[row.row_id]?.[field.inputKey] ?? ""}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [row.row_id]: {
                            ...(current[row.row_id] ?? {}),
                            [field.inputKey]: event.target.value,
                          },
                        }))
                      }
                      placeholder={field.placeholder}
                    />
                  </label>
                ))}
              </div>
              <button
                className="primary-button"
                type="button"
                disabled={submittingRowId !== "" && submittingRowId === row.row_id}
                onClick={() => void submitRow(row)}
              >
                {submittingRowId !== "" && submittingRowId === row.row_id ? "尝试报价中..." : "尝试报价"}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function RejectedEquipmentPanel({ activeStage }: { activeStage?: FormStageSnapshot }) {
  const rowsWithRejections = useMemo(
    () => (activeStage?.items ?? []).filter((row) => row.rejected_equipment.length > 0),
    [activeStage],
  );

  if (!activeStage || rowsWithRejections.length === 0) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3>被筛除设备表</h3>
        <p>逐台展示设备为什么被筛掉；当全部设备都被筛掉时，这里会列出全部候选设备的剔除原因。</p>
      </div>
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
                    <th>待补字段</th>
                  </tr>
                </thead>
                <tbody>
                  {row.rejected_equipment.map((item: EquipmentRejection) => (
                    <tr key={`${row.row_id}-${item.equipment_id}`}>
                      <td>{item.equipment_label || item.equipment_id}</td>
                      <td>{item.reasons.join("；") || "-"}</td>
                      <td>{item.missing_fields.map((field) => MANUAL_LABELS[field] ?? field).join("、") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MatchedEquipmentPanel({ activeStage }: { activeStage?: FormStageSnapshot }) {
  const rowsWithCandidates = useMemo(
    () => (activeStage?.items ?? []).filter((row) => row.candidate_equipment_profiles.length > 0),
    [activeStage],
  );

  if (!activeStage || rowsWithCandidates.length === 0) {
    return null;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h3>匹配设备表</h3>
        <p>展示当前候选设备的非空属性，方便对照设备能力和后续报价依据。</p>
      </div>
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
                      <td>{item.equipment_label || item.equipment_id}</td>
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
    </section>
  );
}

export default function App() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [activeStageId, setActiveStageId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const activeStage: FormStageSnapshot | undefined = useMemo(() => {
    if (!runState) {
      return undefined;
    }
    return (
      runState.form_stages.find((stage) => stage.stage_id === activeStageId) ??
      runState.form_stages.at(-1)
    );
  }, [activeStageId, runState]);

  async function submitFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files || files.length === 0) {
      setError("请先选择至少一个 Word、Excel 或图片文件。");
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
              accept=".docx,.xlsx,.png,.jpg,.jpeg,.bmp,.webp"
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
                <strong>{runState.uploaded_documents.map((item) => item.file_name).join(", ")}</strong>
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

          <section className="panel">
            <div className="panel-header">
              <h3>结构化报价表</h3>
              <p>{activeStage?.label ?? "暂无阶段"} 的完整表格快照。</p>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {COLUMN_DEFS.map((column) => (
                      <th key={column.key}>{column.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeStage && activeStage.items.length > 0 ? (
                    activeStage.items.map((row) => (
                      <tr key={row.row_id} className={row.missing_fields.length > 0 ? "row-warning" : ""}>
                        {COLUMN_DEFS.map((column) => (
                          <td key={`${row.row_id}-${column.key}`}>{formatCell(row, column.key)}</td>
                        ))}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={COLUMN_DEFS.length} className="empty-cell">
                        还没有可展示的结构化表行。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <RejectedEquipmentPanel activeStage={activeStage} />
          <MatchedEquipmentPanel activeStage={activeStage} />

          <ManualEditor runState={runState} onUpdated={(next) => {
            setRunState(next);
            setActiveStageId(next.current_stage);
          }} />
        </>
      ) : null}
    </div>
  );
}
