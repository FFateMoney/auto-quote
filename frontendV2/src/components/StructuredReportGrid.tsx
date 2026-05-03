/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Check, ChevronRight, Edit3, Hash, List, Loader2, Type, X} from 'lucide-react';
import {motion} from 'motion/react';
import {fetchTestTypes, resumeRun, toErrorMessage} from '../api';
import type {
  ExtraStandardRequirement,
  FormRow,
  FormStageSnapshot,
  RunState,
  TestTypeOption,
} from '../types';

type RangeInputKey =
  | 'required_temp_range'
  | 'required_humidity_range'
  | 'required_freq_range'
  | 'required_accel_range'
  | 'required_displacement_range'
  | 'required_irradiance_range'
  | 'required_water_temp_range'
  | 'required_water_flow_range';

type DisplayFieldKey = keyof FormRow | RangeInputKey;

type EditableFieldKey =
  | 'canonical_test_type'
  | 'pricing_quantity'
  | 'sample_count'
  | 'repeat_count'
  | 'sample_length_mm'
  | 'sample_width_mm'
  | 'sample_height_mm'
  | 'sample_weight_kg'
  | 'required_temp_change_rate'
  | RangeInputKey;

type ColumnDef = {
  key: DisplayFieldKey;
  label: string;
  type: 'text' | 'select' | 'number';
};

type RowDrafts = Partial<Record<EditableFieldKey, string>>;

type TestTypePickerState = {
  rowId: string;
  currentValue: string;
} | null;

const BASE_COLUMN_DEFS: ColumnDef[] = [
  {key: 'canonical_test_type', label: '标准试验类型', type: 'select'},
  {key: 'standard_codes', label: '标准号', type: 'text'},
  {key: 'pricing_mode', label: '计价单位', type: 'text'},
  {key: 'pricing_quantity', label: '计价数量', type: 'number'},
  {key: 'sample_count', label: '样品件数', type: 'number'},
  {key: 'repeat_count', label: '重复次数', type: 'number'},
  {key: 'sample_length_mm', label: '样品长(mm)', type: 'number'},
  {key: 'sample_width_mm', label: '样品宽(mm)', type: 'number'},
  {key: 'sample_height_mm', label: '样品高(mm)', type: 'number'},
  {key: 'sample_weight_kg', label: '样品重量(kg)', type: 'number'},
  {key: 'extra_standard_requirements', label: '额外标准要求', type: 'text'},
  {key: 'selected_equipment_id', label: '选中设备', type: 'text'},
  {key: 'candidate_equipment_ids', label: '候选设备', type: 'text'},
  {key: 'base_fee', label: '基本金', type: 'number'},
  {key: 'unit_price', label: '单价', type: 'number'},
  {key: 'formula', label: '公式', type: 'text'},
  {key: 'total_price', label: '总价', type: 'number'},
  {key: 'stage_status', label: '状态', type: 'text'},
];

const EDITABLE_FIELD_DEFS: Record<EditableFieldKey, {label: string; inputMode: 'text' | 'decimal'}> = {
  canonical_test_type: {label: '标准试验类型', inputMode: 'text'},
  pricing_quantity: {label: '计价数量', inputMode: 'decimal'},
  sample_count: {label: '样品件数', inputMode: 'decimal'},
  repeat_count: {label: '重复次数', inputMode: 'decimal'},
  sample_length_mm: {label: '样品长(mm)', inputMode: 'decimal'},
  sample_width_mm: {label: '样品宽(mm)', inputMode: 'decimal'},
  sample_height_mm: {label: '样品高(mm)', inputMode: 'decimal'},
  sample_weight_kg: {label: '样品重量(kg)', inputMode: 'decimal'},
  required_temp_range: {label: '温度要求', inputMode: 'text'},
  required_humidity_range: {label: '湿度要求', inputMode: 'text'},
  required_temp_change_rate: {label: '温变速率', inputMode: 'decimal'},
  required_freq_range: {label: '频率要求', inputMode: 'text'},
  required_accel_range: {label: '加速度要求', inputMode: 'text'},
  required_displacement_range: {label: '位移要求', inputMode: 'text'},
  required_irradiance_range: {label: '辐照要求', inputMode: 'text'},
  required_water_temp_range: {label: '水温要求', inputMode: 'text'},
  required_water_flow_range: {label: '水流量要求', inputMode: 'text'},
};

const RANGE_INPUT_GROUPS: Array<{
  inputKey: RangeInputKey;
  minField: keyof FormRow;
  maxField: keyof FormRow;
  label: string;
}> = [
  {inputKey: 'required_temp_range', minField: 'required_temp_min', maxField: 'required_temp_max', label: '温度要求'},
  {inputKey: 'required_humidity_range', minField: 'required_humidity_min', maxField: 'required_humidity_max', label: '湿度要求'},
  {inputKey: 'required_freq_range', minField: 'required_freq_min', maxField: 'required_freq_max', label: '频率要求'},
  {inputKey: 'required_accel_range', minField: 'required_accel_min', maxField: 'required_accel_max', label: '加速度要求'},
  {inputKey: 'required_displacement_range', minField: 'required_displacement_min', maxField: 'required_displacement_max', label: '位移要求'},
  {inputKey: 'required_irradiance_range', minField: 'required_irradiance_min', maxField: 'required_irradiance_max', label: '辐照要求'},
  {inputKey: 'required_water_temp_range', minField: 'required_water_temp_min', maxField: 'required_water_temp_max', label: '水温要求'},
  {inputKey: 'required_water_flow_range', minField: 'required_water_flow_min', maxField: 'required_water_flow_max', label: '水流量要求'},
];

const DYNAMIC_COLUMN_DEFS: ColumnDef[] = [
  {key: 'required_temp_range', label: '温度要求', type: 'text'},
  {key: 'required_humidity_range', label: '湿度要求', type: 'text'},
  {key: 'required_temp_change_rate', label: '温变速率', type: 'number'},
  {key: 'required_freq_range', label: '频率要求', type: 'text'},
  {key: 'required_accel_range', label: '加速度要求', type: 'text'},
  {key: 'required_displacement_range', label: '位移要求', type: 'text'},
  {key: 'required_irradiance_range', label: '辐照要求', type: 'text'},
  {key: 'required_water_temp_range', label: '水温要求', type: 'text'},
  {key: 'required_water_flow_range', label: '水流量要求', type: 'text'},
];

const MANUAL_LABELS: Record<string, string> = {
  canonical_test_type: '标准试验类型',
  pricing_quantity: '计价数量',
  sample_count: '样品件数',
  repeat_count: '重复次数',
  sample_length_mm: '样品长(mm)',
  sample_width_mm: '样品宽(mm)',
  sample_height_mm: '样品高(mm)',
  sample_weight_kg: '样品重量(kg)',
  required_temp_min: '最低温度',
  required_temp_max: '最高温度',
  required_humidity_min: '最低湿度',
  required_humidity_max: '最高湿度',
  required_temp_change_rate: '温变速率',
  required_freq_min: '最低频率',
  required_freq_max: '最高频率',
  required_accel_min: '最低加速度',
  required_accel_max: '最高加速度',
  required_displacement_min: '最小位移',
  required_displacement_max: '最大位移',
  required_irradiance_min: '最低辐照',
  required_irradiance_max: '最高辐照',
  required_water_temp_min: '最低水温',
  required_water_temp_max: '最高水温',
  required_water_flow_min: '最小流量',
  required_water_flow_max: '最大流量',
};

export const StructuredReportGrid: React.FC<{
  activeStage?: FormStageSnapshot;
  runState: RunState;
  onUpdated: (next: RunState) => void;
}> = ({activeStage, runState, onUpdated}) => {
  const rows = activeStage?.items ?? [];
  const [savedDrafts, setSavedDrafts] = React.useState<Record<string, RowDrafts>>({});
  const [editingValues, setEditingValues] = React.useState<Record<string, RowDrafts>>({});
  const [editingFields, setEditingFields] = React.useState<Record<string, Partial<Record<EditableFieldKey, boolean>>>>({});
  const [submittingRowId, setSubmittingRowId] = React.useState('');
  const [error, setError] = React.useState('');
  const [testTypePicker, setTestTypePicker] = React.useState<TestTypePickerState>(null);
  const [testTypeOptions, setTestTypeOptions] = React.useState<TestTypeOption[]>([]);
  const [testTypeLoading, setTestTypeLoading] = React.useState(false);
  const [testTypeError, setTestTypeError] = React.useState('');
  const pickerRow = testTypePicker ? rows.find((row) => row.row_id === testTypePicker.rowId) : undefined;

  const columnDefs = React.useMemo(() => {
    const dynamic = DYNAMIC_COLUMN_DEFS.filter((column) => shouldShowDynamicField(rows, column.key));
    return [...BASE_COLUMN_DEFS.slice(0, 10), ...dynamic, ...BASE_COLUMN_DEFS.slice(10)];
  }, [rows]);

  React.useEffect(() => {
    setSavedDrafts({});
    setEditingValues({});
    setEditingFields({});
    setError('');
  }, [activeStage?.stage_id]);

  React.useEffect(() => {
    if (!testTypePicker || testTypeOptions.length > 0 || testTypeLoading) {
      return;
    }
    let cancelled = false;
    async function loadOptions() {
      setTestTypeLoading(true);
      setTestTypeError('');
      try {
        const data = await fetchTestTypes();
        if (cancelled) {
          return;
        }
        setTestTypeOptions(data.items);
        if (data.load_error) {
          setTestTypeError(`目录加载告警：${data.load_error}`);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setTestTypeError(toErrorMessage(fetchError, '无法获取标准试验类型目录'));
        }
      } finally {
        if (!cancelled) {
          setTestTypeLoading(false);
        }
      }
    }
    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [testTypePicker, testTypeOptions.length]);

  function startEditing(row: FormRow, field: EditableFieldKey) {
    if (field === 'canonical_test_type') {
      setTestTypePicker({rowId: row.row_id, currentValue: getRawFieldString(row, field)});
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

  function setEditingValue(rowId: string, field: EditableFieldKey, value: string) {
    setEditingValues((current) => ({
      ...current,
      [rowId]: {
        ...(current[rowId] ?? {}),
        [field]: value,
      },
    }));
  }

  function saveField(row: FormRow, field: EditableFieldKey) {
    const nextValue = editingValues[row.row_id]?.[field] ?? '';
    saveDraft(row, field, nextValue);
    setEditingValues((current) => {
      const rowDraft = {...(current[row.row_id] ?? {})};
      delete rowDraft[field];
      return {...current, [row.row_id]: rowDraft};
    });
    setEditingFields((current) => ({
      ...current,
      [row.row_id]: {
        ...(current[row.row_id] ?? {}),
        [field]: false,
      },
    }));
  }

  function saveDraft(row: FormRow, field: EditableFieldKey, value: string) {
    const originalValue = getRawFieldString(row, field);
    setSavedDrafts((current) => {
      const rowDraft = {...(current[row.row_id] ?? {})};
      if (value === originalValue) {
        delete rowDraft[field];
      } else {
        rowDraft[field] = value;
      }
      if (Object.keys(rowDraft).length === 0) {
        const {[row.row_id]: _removed, ...rest} = current;
        return rest;
      }
      return {...current, [row.row_id]: rowDraft};
    });
  }

  function chooseTestType(row: FormRow, selectedName: string) {
    saveDraft(row, 'canonical_test_type', selectedName);
    setTestTypePicker(null);
  }

  async function submitRowChanges(row: FormRow) {
    const rowDraft = savedDrafts[row.row_id] ?? {};
    if (Object.keys(rowDraft).length === 0) {
      setError('请先保存至少一个字段修改后再重新报价。');
      return;
    }
    setSubmittingRowId(row.row_id);
    setError('');
    try {
      const next = await resumeRun(runState.run_id, {
        row_id: row.row_id,
        field_values: rowDraft,
      });
      setSavedDrafts((current) => {
        const {[row.row_id]: _removed, ...rest} = current;
        return rest;
      });
      onUpdated(next);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法连接后端重新报价接口'));
    } finally {
      setSubmittingRowId('');
    }
  }

  if (!activeStage) {
    return <div className="glass-panel p-12 text-center text-slate-400">还没有可展示的结构化表行。</div>;
  }

  return (
    <div className="mb-12">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <ChevronRight className="text-indigo-400" />
            {activeStage.label}
          </h3>
          <p className="text-xs text-slate-400 mt-1 font-mono">Stage ID: {activeStage.stage_id}</p>
        </div>
        <div className="text-xs text-slate-500 max-w-md lg:text-right leading-relaxed italic">
          最终报价的完整表格快照；指定字段可人工修正并重新报价。
        </div>
      </div>

      {error ? <div className="mb-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
      {activeStage.notes.length > 0 ? (
        <div className="mb-5 flex flex-wrap gap-2">
          {activeStage.notes.map((note, index) => (
            <span key={`${activeStage.stage_id}-${index}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">
              {note}
            </span>
          ))}
        </div>
      ) : null}

      {rows.length > 0 ? (
        <div className="space-y-8">
          {rows.map((row) => (
            <section key={row.row_id} className={`glass-panel p-5 ${row.missing_fields.length > 0 ? 'ring-1 ring-amber-200 bg-amber-50/20' : ''}`}>
              <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <h4 className="truncate text-lg font-bold text-slate-800">{row.raw_test_type || row.canonical_test_type || '未命名试验'}</h4>
                  <p className="mt-1 text-xs font-mono text-slate-400">Row ID: {row.row_id}</p>
                </div>
                {row.missing_fields.length > 0 ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                    待补录：{row.missing_fields.map((field) => MANUAL_LABELS[field] ?? field).join('、')}
                  </div>
                ) : null}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-4">
                {columnDefs.map((column, index) => {
                  const editable = isEditableField(column.key);
                  const editing = editable ? editingFields[row.row_id]?.[column.key] : false;
                  const value = formatCell(row, column.key, savedDrafts);
                  const draftSaved = editable && savedDrafts[row.row_id]?.[column.key] != null;
                  return (
                    <motion.div
                      key={`${row.row_id}-${column.key}`}
                      initial={{opacity: 0, scale: 0.97}}
                      animate={{opacity: 1, scale: 1}}
                      transition={{delay: index * 0.01}}
                      className={`glass-panel p-4 flex flex-col justify-between group relative overflow-hidden transition-all hover:ring-2 hover:ring-indigo-200 ${value === '-' ? 'bg-slate-50/50' : 'bg-white'}`}
                    >
                      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-20 transition-opacity">
                        {column.type === 'number' ? <Hash size={14} /> : column.type === 'select' ? <List size={14} /> : <Type size={14} />}
                      </div>
                      <div>
                        <p className="text-[11px] font-bold text-slate-400 leading-tight mb-2 min-h-8">{column.label}</p>
                        {editable && editing ? (
                          <input
                            className="w-full rounded-lg border border-indigo-100 bg-white px-2 py-1.5 text-sm font-semibold text-indigo-900 outline-none focus:border-indigo-300"
                            type={EDITABLE_FIELD_DEFS[column.key].inputMode === 'decimal' ? 'number' : 'text'}
                            step={EDITABLE_FIELD_DEFS[column.key].inputMode === 'decimal' ? 'any' : undefined}
                            value={editingValues[row.row_id]?.[column.key] ?? ''}
                            onChange={(event) => setEditingValue(row.row_id, column.key, event.target.value)}
                            placeholder={EDITABLE_FIELD_DEFS[column.key].label}
                          />
                        ) : (
                          <div
                            className={`break-words text-base font-semibold font-mono ${value === '-' ? 'text-slate-300' : 'text-indigo-900'}`}
                            title={value}
                            style={column.key === 'extra_standard_requirements' ? {whiteSpace: 'pre-wrap'} : undefined}
                          >
                            {value}
                          </div>
                        )}
                      </div>
                      {editable ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {editing ? (
                            <>
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 rounded border border-emerald-100 bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700 hover:border-emerald-200"
                                onClick={() => saveField(row, column.key)}
                              >
                                <Check size={10} />
                                保存
                              </button>
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 rounded border border-slate-100 bg-slate-50 px-2 py-1 text-[10px] font-bold text-slate-500 hover:border-slate-200"
                                onClick={() => setEditingFields((current) => ({...current, [row.row_id]: {...(current[row.row_id] ?? {}), [column.key]: false}}))}
                              >
                                <X size={10} />
                                取消
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              className="inline-flex items-center gap-1.5 text-[10px] font-bold text-indigo-500 hover:text-indigo-700 transition-colors uppercase bg-indigo-50/50 group-hover:bg-indigo-50 px-2 py-1 rounded border border-transparent hover:border-indigo-100"
                              onClick={() => startEditing(row, column.key)}
                            >
                              <Edit3 size={10} />
                              {column.key === 'canonical_test_type' ? '选择' : '编辑'}
                            </button>
                          )}
                          {draftSaved && !editing ? <span className="text-[10px] font-bold text-amber-600">已暂存</span> : null}
                        </div>
                      ) : null}
                    </motion.div>
                  );
                })}
              </div>

              {Object.keys(savedDrafts[row.row_id] ?? {}).length > 0 ? (
                <div className="mt-5 flex flex-col gap-3 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <p className="text-sm font-medium text-slate-600">
                    已保存 {Object.keys(savedDrafts[row.row_id] ?? {}).length} 个字段修改，可基于人工修正结果重新报价。
                  </p>
                  <button
                    type="button"
                    className="btn-primary inline-flex items-center justify-center gap-2"
                    disabled={submittingRowId !== '' && submittingRowId === row.row_id}
                    onClick={() => void submitRowChanges(row)}
                  >
                    {submittingRowId === row.row_id ? <Loader2 size={15} className="animate-spin" /> : null}
                    {submittingRowId === row.row_id ? '重新报价中...' : '按已保存修改重新报价'}
                  </button>
                </div>
              ) : null}
            </section>
          ))}
        </div>
      ) : (
        <div className="glass-panel p-12 text-center text-slate-400">还没有可展示的结构化表行。</div>
      )}

      {testTypePicker ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="presentation" onClick={() => setTestTypePicker(null)}>
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label="选择标准试验类型"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-4">
              <div>
                <div className="text-base font-bold text-slate-800">选择标准试验类型</div>
                <div className="mt-1 text-xs text-slate-400">当前值：{testTypePicker.currentValue || '未填写'}</div>
              </div>
              <button type="button" className="btn-secondary text-xs" onClick={() => setTestTypePicker(null)}>关闭</button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-4">
              {testTypeLoading ? <div className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-400">正在加载标准试验类型目录...</div> : null}
              {!testTypeLoading && testTypeError ? <div className="mb-3 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{testTypeError}</div> : null}
              {!testTypeLoading && pickerRow && testTypeOptions.length > 0 ? (
                <div className="grid gap-2">
                  {testTypeOptions.map((option) => {
                    const selectedValue = savedDrafts[pickerRow.row_id]?.canonical_test_type ?? getRawFieldString(pickerRow, 'canonical_test_type');
                    const isSelected = selectedValue === option.name;
                    return (
                      <button
                        key={`${pickerRow.row_id}-${option.id}`}
                        type="button"
                        className={`rounded-lg border px-4 py-3 text-left transition-colors ${isSelected ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-700 hover:border-indigo-200'}`}
                        onClick={() => chooseTestType(pickerRow, option.name)}
                      >
                        <span className="block text-sm font-bold">{option.name}</span>
                        <span className="mt-1 block text-xs text-slate-400">
                          计价单位：{option.pricing_mode || '-'}{option.aliases.length > 0 ? ` | 别名：${option.aliases.join('、')}` : ''}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {!testTypeLoading && !testTypeError && testTypeOptions.length === 0 ? (
                <div className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-400">目录里还没有可选的标准试验类型。</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

function isEditableField(key: DisplayFieldKey): key is EditableFieldKey {
  return key in EDITABLE_FIELD_DEFS;
}

function findRangeGroup(key: DisplayFieldKey) {
  return RANGE_INPUT_GROUPS.find((group) => group.inputKey === key);
}

function getCoveredFieldNames(key: DisplayFieldKey): string[] {
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return [String(rangeGroup.minField), String(rangeGroup.maxField)];
  }
  return [String(key)];
}

function formatScalarValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(', ') : '-';
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value == null || value === '' ? '-' : String(value);
}

function formatRangeValue(minValue: unknown, maxValue: unknown): string {
  const minText = minValue == null || minValue === '' ? '' : String(minValue);
  const maxText = maxValue == null || maxValue === '' ? '' : String(maxValue);
  if (!minText && !maxText) {
    return '-';
  }
  if (minText && maxText) {
    return `${minText}～${maxText}`;
  }
  return minText || maxText;
}

function formatExtraRequirement(item: ExtraStandardRequirement): string {
  const name = item.requirement_name || '未命名要求';
  const body = item.requirement_text || '-';
  const source = item.source_section ? `（${item.source_section}）` : '';
  return `${name}：${body}${source}`;
}

function formatStatus(row: FormRow): string {
  if (row.stage_status) {
    return row.stage_status;
  }
  return row.total_price != null ? '报价成功' : '报价失败';
}

function getRawFieldString(row: FormRow, key: EditableFieldKey): string {
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    const formatted = formatRangeValue(row[rangeGroup.minField], row[rangeGroup.maxField]);
    return formatted === '-' ? '' : formatted;
  }
  const value = row[key];
  return value == null ? '' : String(value);
}

function getCommittedFieldValue(row: FormRow, key: EditableFieldKey, savedDrafts: Record<string, RowDrafts>): string {
  const saved = savedDrafts[row.row_id]?.[key];
  if (saved != null) {
    return saved === '' ? '-' : saved;
  }
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return formatRangeValue(row[rangeGroup.minField], row[rangeGroup.maxField]);
  }
  return formatScalarValue(row[key]);
}

function formatCell(row: FormRow, key: DisplayFieldKey, savedDrafts: Record<string, RowDrafts>): string {
  if (isEditableField(key)) {
    return getCommittedFieldValue(row, key, savedDrafts);
  }
  if (key === 'extra_standard_requirements') {
    return row.extra_standard_requirements.length > 0 ? row.extra_standard_requirements.map(formatExtraRequirement).join('\n') : '-';
  }
  if (key === 'stage_status') {
    return formatStatus(row);
  }
  return formatScalarValue(row[key]);
}

function shouldShowDynamicField(rows: FormRow[], key: DisplayFieldKey): boolean {
  const coveredFields = new Set(getCoveredFieldNames(key));
  const rangeGroup = findRangeGroup(key);
  if (rangeGroup) {
    return rows.some((row) => {
      const minValue = row[rangeGroup.minField];
      const maxValue = row[rangeGroup.maxField];
      return (
        minValue != null ||
        maxValue != null ||
        row.missing_fields.some((field) => coveredFields.has(field)) ||
        row.planned_standard_fields.some((field) => coveredFields.has(field)) ||
        row.discovered_standard_fields.some((field) => coveredFields.has(field))
      );
    });
  }
  return rows.some((row) => {
    const value = row[key as keyof FormRow];
    return (
      (value != null && value !== '' && (!Array.isArray(value) || value.length > 0)) ||
      row.missing_fields.some((field) => coveredFields.has(field)) ||
      row.planned_standard_fields.some((field) => coveredFields.has(field)) ||
      row.discovered_standard_fields.some((field) => coveredFields.has(field))
    );
  });
}
