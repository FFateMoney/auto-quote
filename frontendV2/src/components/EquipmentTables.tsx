/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Info, Loader2, RefreshCw, XCircle} from 'lucide-react';
import {resumeRun, toErrorMessage} from '../api';
import type {EquipmentProfile, FormRow, FormStageSnapshot, RunState} from '../types';

const EQUIPMENT_ATTR_LABELS: Record<string, string> = {
  volume_m3: '容积(m3)',
  length_mm: '长度(mm)',
  width_mm: '宽度(mm)',
  height_mm: '高度(mm)',
  power_kwh: '功率(kWh)',
  max_load_kg: '最大载荷(kg)',
  temp_min: '最低温度',
  temp_max: '最高温度',
  humidity_min: '最低湿度',
  humidity_max: '最高湿度',
  temp_change_rate_min: '最小温变速率',
  temp_change_rate_max: '最大温变速率',
  constraints_info: '约束说明',
  status: '状态',
  freq_min: '最低频率',
  freq_max: '最高频率',
  accel_min: '最低加速度',
  accel_max: '最高加速度',
  displacement_min: '最小位移',
  displacement_max: '最大位移',
  irradiance_min: '最低辐照',
  irradiance_max: '最高辐照',
  water_temp_min: '最低水温',
  water_temp_max: '最高水温',
  water_flow_min: '最小流量',
  water_flow_max: '最大流量',
};

export const EquipmentTables: React.FC<{
  activeStage?: FormStageSnapshot;
  runState: RunState;
  onUpdated: (next: RunState) => void;
}> = ({activeStage, runState, onUpdated}) => {
  const [submittingKey, setSubmittingKey] = React.useState('');
  const [error, setError] = React.useState('');
  const rows = activeStage?.items ?? [];
  const rowsWithCandidates = rows.filter((row) => row.candidate_equipment_profiles.length > 0);
  const rowsWithRejections = rows.filter((row) => row.rejected_equipment.length > 0);

  async function selectEquipment(row: FormRow, equipment: EquipmentProfile) {
    if (submittingKey !== '') {
      return;
    }
    const key = `${row.row_id}:${equipment.equipment_id}`;
    setSubmittingKey(key);
    setError('');
    try {
      const next = await resumeRun(runState.run_id, {
        row_id: row.row_id,
        field_values: {selected_equipment_id: equipment.equipment_id},
      });
      onUpdated(next);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法连接后端设备切换接口'));
    } finally {
      setSubmittingKey('');
    }
  }

  if (!activeStage) {
    return null;
  }

  return (
    <div className="space-y-12">
      {error ? <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

      <section>
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between mb-4">
          <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            匹配设备表
            <span className="text-[10px] bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full border border-indigo-100">
              {rowsWithCandidates.reduce((total, row) => total + row.candidate_equipment_profiles.length, 0)} 台候选
            </span>
          </h3>
          <p className="text-xs text-slate-400 italic">展示当前候选设备的非空属性，方便对照设备能力。</p>
        </div>

        {rowsWithCandidates.length > 0 ? (
          <div className="space-y-4">
            {rowsWithCandidates.map((row) => (
              <div key={`${row.row_id}-matched`} className="glass-panel overflow-hidden">
                <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-3">
                  <h4 className="font-bold text-slate-800">{row.raw_test_type || row.canonical_test_type || row.row_id}</h4>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-slate-50/80 border-b border-slate-200">
                      <tr>
                        <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase">设备名称</th>
                        <th className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase">关键属性明细</th>
                        <th className="px-6 py-4 text-right"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {row.candidate_equipment_profiles.map((device) => {
                        const selected = row.selected_equipment_id === device.equipment_id;
                        const key = `${row.row_id}:${device.equipment_id}`;
                        return (
                          <tr key={key} className="group hover:bg-slate-50/50 transition-colors">
                            <td className="px-6 py-4 align-top">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className="font-bold text-slate-800">{device.equipment_label || device.equipment_id}</span>
                                {selected ? (
                                  <span className="flex items-center gap-1 text-[9px] font-bold bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded uppercase border border-emerald-100">
                                    当前选中
                                  </span>
                                ) : null}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm leading-relaxed">
                              <div className="flex flex-wrap gap-x-4 gap-y-2">
                                {Object.entries(device.attributes).length > 0 ? Object.entries(device.attributes).map(([attrKey, value]) => (
                                  <div key={attrKey} className="flex items-center gap-1.5">
                                    <span className="text-slate-400 text-xs">{EQUIPMENT_ATTR_LABELS[attrKey] ?? attrKey}:</span>
                                    <span className="text-slate-700 font-mono text-xs">{formatValue(value)}</span>
                                  </div>
                                )) : <span className="text-xs text-slate-400">暂无属性</span>}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-right align-top">
                              {!selected ? (
                                <button
                                  type="button"
                                  className="btn-secondary group-hover:bg-white text-xs py-1.5 px-3 flex items-center gap-2 ml-auto"
                                  disabled={submittingKey !== ''}
                                  onClick={() => void selectEquipment(row, device)}
                                >
                                  {submittingKey === key ? <Loader2 size={12} className="animate-spin text-indigo-500" /> : <RefreshCw size={12} className="text-indigo-500" />}
                                  {submittingKey === key ? '切换中...' : '选用并重新报价'}
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="border-2 border-dashed border-slate-100 rounded-2xl p-12 text-center text-slate-300 italic">
            当前阶段没有候选设备。
          </div>
        )}
      </section>

      <section>
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between mb-4">
          <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            被筛选设备表
            {rowsWithRejections.length > 0 ? <span className="text-red-500"><XCircle size={18} /></span> : null}
          </h3>
          <p className="text-xs text-slate-400 italic">展示当前阶段基于限制条件的筛除结果。</p>
        </div>

        {rowsWithRejections.length > 0 ? (
          <div className="grid gap-4">
            {rowsWithRejections.map((row) => (
              <div key={`${row.row_id}-rejected`} className="glass-panel overflow-hidden">
                <div className="border-b border-slate-100 bg-red-50/30 px-6 py-3">
                  <h4 className="font-bold text-slate-800">{row.raw_test_type || row.canonical_test_type || row.row_id}</h4>
                </div>
                <div className="grid gap-3 p-4">
                  {row.rejected_equipment.map((device) => (
                    <div key={`${row.row_id}-${device.equipment_id}`} className="rounded-xl border border-red-100 bg-red-50/10 p-4 flex items-start justify-between">
                      <div className="flex gap-4">
                        <div className="w-10 h-10 rounded-lg bg-red-50 border border-red-100 flex items-center justify-center text-red-500 shrink-0">
                          <Info size={18} />
                        </div>
                        <div>
                          <h5 className="font-bold text-slate-800 mb-1">{device.equipment_label || device.equipment_id}</h5>
                          <p className="text-sm text-red-600 font-medium">原因: {device.reasons.join('；') || '-'}</p>
                          {device.missing_fields.length > 0 ? (
                            <div className="mt-2 text-[10px] text-slate-400 uppercase">
                              缺失字段: {device.missing_fields.join('、')}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="border-2 border-dashed border-slate-100 rounded-2xl p-12 text-center text-slate-300 italic">
            当前阶段没有被筛除设备。
          </div>
        )}
      </section>
    </div>
  );
};

function formatValue(value: unknown): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value == null || value === '' ? '-' : String(value);
}
