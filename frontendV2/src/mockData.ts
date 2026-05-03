/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { RunStatus, StructuredReport, Equipment } from './types';

export const mockRunStatus: RunStatus = {
  runId: "标准检索test_20260501224339",
  overallStatus: 'waiting_manual_input',
  currentStage: "final_quoted",
  uploadedFile: "标准检索test.xlsx"
};

export const mockReport: StructuredReport = {
  id: "row_27ed786b18634b05a3141269c7123ca3",
  title: "振动测试",
  fields: [
    { id: '1', label: '标准试验类型', value: '振动', type: 'select', editable: true },
    { id: '2', label: '标准号', value: 'MBN 10438-2015', type: 'text' },
    { id: '3', label: '计价单位', value: '小时', type: 'text' },
    { id: '4', label: '计价数量', value: 42, type: 'number', editable: true },
    { id: '5', label: '样品件数', value: '-', type: 'number', editable: true },
    { id: '6', label: '重复次数', value: '-', type: 'number', editable: true },
    { id: '7', label: '样品长(mm)', value: '-', type: 'number', editable: true },
    { id: '8', label: '样品宽(mm)', value: '-', type: 'number', editable: true },
    { id: '9', label: '样品高(mm)', value: '-', type: 'number', editable: true },
    { id: '10', label: '温度要求', value: '-', type: 'text', editable: true },
    { id: '11', label: '湿度要求', value: '-', type: 'text', editable: true },
    { id: '12', label: '温变速率', value: '-', type: 'text', editable: true },
    { id: '13', label: '频率要求', value: '-', type: 'text', editable: true },
    { id: '14', label: '加速度要求', value: '-', type: 'text', editable: true },
    { id: '15', label: '位移要求', value: '-', type: 'text', editable: true },
    { id: '16', label: '样品重量(kg)', value: '-', type: 'number', editable: true },
    { id: '17', label: '额外标准要求', value: '-', type: 'text', editable: true },
    { id: '18', label: '选中设备', value: 'F10', type: 'text' },
    { id: '19', label: '候选设备', value: 'F10, F6, N6, F1f, N1f, F3, N3, F5f, N5f', type: 'text' },
    { id: '20', label: '基本金', value: 1500, type: 'number' },
    { id: '21', label: '单价', value: '-', type: 'number' },
    { id: '22', label: '公式', value: '-', type: 'text' },
    { id: '23', label: '总价', value: '-', type: 'number' },
    { id: '24', label: '状态', value: '报价失败', type: 'text' },
  ]
};

export const mockEquipment: Equipment[] = [
  {
    id: 'F10',
    name: 'F10',
    status: 'selected',
    attributes: {
      '长度(mm)': 500,
      '宽度(mm)': 500,
      '功率(kWh)': 21,
      '最大载荷(kg)': 300,
      '状态': 'active',
      '最高加速度': 100,
      '最低加速度': 0,
      '最大位移': 51,
      '最小位移': 0,
      '最高频率': 2000,
      '最低频率': 5
    }
  },
  {
    id: 'F6',
    name: 'F6',
    status: 'available',
    attributes: {
      '长度(mm)': 1000,
      '宽度(mm)': 1000,
      '功率(kWh)': 37.08,
      '最大载荷(kg)': 500,
      '最低温度': -50,
      '最高温度': 120,
      '最大温变速率': 8
    }
  },
  {
    id: 'EX1',
    name: 'Old Oven 200',
    status: 'excluded',
    exclusionReason: '温控范围不匹配 (所需: -50~120℃, 设备: 0~100℃)',
    attributes: {
      '型号': 'V1',
      '状态': 'maintenance'
    }
  }
];
