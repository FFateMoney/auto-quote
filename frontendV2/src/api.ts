import type {ResumeRequest, RunHistoryResponse, RunState, TestTypeAliasesUpdateResponse, TestTypeCatalogResponse} from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '');

const REQUEST_TIMEOUT_MS = 20_000;
const RUN_REQUEST_TIMEOUT_MS = 10 * 60_000;

type AuthSessionResponse = {
  auth_enabled: boolean;
  authenticated: boolean;
};

type LoginResponse = {
  authenticated: boolean;
  expires_in: number;
};

export type AgentRunSnapshot = {
  run_id: string;
  status: string;
  uploaded_file: string;
  created_at: string;
  updated_at: string;
  agent_return_code: number | null;
};

export type AgentQuotationItem = {
  quote_id: string;
  test_project_id: number | null;
  fixed_fields: Record<string, unknown>;
  special_fields: Record<string, unknown>;
  base_fee: number | null;
  base_fee_override?: number | null;
  unit_price: number | null;
  pricing_mode: unknown;
  pricing_quantity: unknown;
  total_price: number | null;
  selected_device_code: string | null;
  eligible_devices: AgentEquipmentCandidate[];
  specification_options: AgentSpecificationOption[];
};

export type AgentSpecificationOption = {
  test_project_id: number;
  specification: string;
  pricing_mode: string;
};

export type AgentEquipmentCandidate = {
  device_code: string;
  power_kwh: number | null;
  capabilities: Record<string, unknown>;
};

export type AgentQuotationResults = {
  items: AgentQuotationItem[];
};

export type HistoricalQuotationSaveResult = {
  saved_count: number;
};

export type CatalogTestProject = {
  id: number;
  standard_type: string;
  test_item: string;
  max_specification: string;
  pricing_mode: string;
  base_fee: number;
  unit_price: number;
  applicable_device_codes: string[];
  aliases: string[];
};

export type CatalogDevice = {
  id: number;
  device_code: string;
  capabilities: Record<string, unknown>;
};

export type CatalogDevicesResponse = {
  capability_fields: string[];
  items: CatalogDevice[];
};

export type CatalogTestProjectDraft = Omit<CatalogTestProject, 'id' | 'aliases'>;

export type CatalogDeviceDraft = {
  device_code: string;
  capabilities: Record<string, unknown>;
};

export function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DOMException && error.name === 'AbortError') {
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
    return await fetch(input, {...init, credentials: 'include', signal: controller.signal});
  } finally {
    window.clearTimeout(timer);
  }
}

async function parseJsonResponse<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent('autoquote:auth-expired'));
    }
    throw new Error(`${action}失败，HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchAuthSession(): Promise<AuthSessionResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/auth/session`);
  return parseJsonResponse<AuthSessionResponse>(response, '检查登录状态');
}

export async function loginWithPassword(password: string): Promise<LoginResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password}),
  });
  return parseJsonResponse<LoginResponse>(response, '登录');
}

export async function logout(): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE}/auth/logout`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`退出登录失败，HTTP ${response.status}`);
  }
}

export async function createRun(files: File[]): Promise<AgentRunSnapshot> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  formData.append('quote_mode', 'single');
  const response = await fetchWithTimeout(
    `${API_BASE}/runs`,
    {
      method: 'POST',
      body: formData,
    },
    RUN_REQUEST_TIMEOUT_MS,
  );
  return parseJsonResponse<AgentRunSnapshot>(response, '创建运行');
}

export async function fetchAgentRun(runId: string): Promise<AgentRunSnapshot> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
  return parseJsonResponse<AgentRunSnapshot>(response, '获取运行状态');
}

export async function fetchAgentQuotationResults(runId: string): Promise<AgentQuotationResults> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/quotation-results`);
  return parseJsonResponse<AgentQuotationResults>(response, '获取报价结果');
}

export async function fetchCatalogTestProjects(): Promise<{items: CatalogTestProject[]}> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects`);
  return parseJsonResponse<{items: CatalogTestProject[]}>(response, '获取测试项目表');
}

export async function fetchDeletedCatalogTestProjects(): Promise<{items: CatalogTestProject[]}> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects/deleted`);
  return parseJsonResponse<{items: CatalogTestProject[]}>(response, '获取已删除测试项目');
}

export async function createCatalogTestProject(draft: CatalogTestProjectDraft): Promise<CatalogTestProject> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(draft),
  });
  return (await parseJsonResponse<{item: CatalogTestProject}>(response, '新增测试项目')).item;
}

export async function updateCatalogTestProject(testProjectId: number, draft: CatalogTestProjectDraft): Promise<CatalogTestProject> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects/${encodeURIComponent(testProjectId)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(draft),
  });
  return (await parseJsonResponse<{item: CatalogTestProject}>(response, '保存测试项目')).item;
}

export async function updateCatalogTestProjectAliases(testProjectId: number, aliases: string[]): Promise<CatalogTestProject> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects/${encodeURIComponent(testProjectId)}/aliases`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({aliases}),
  });
  return (await parseJsonResponse<{item: CatalogTestProject}>(response, '保存测试项目别名')).item;
}

export async function deleteCatalogTestProject(testProjectId: number): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects/${encodeURIComponent(testProjectId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`删除测试项目失败，HTTP ${response.status}`);
  }
}

export async function restoreCatalogTestProject(testProjectId: number): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-projects/${encodeURIComponent(testProjectId)}/restore`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`恢复测试项目失败，HTTP ${response.status}`);
  }
}

export async function fetchCatalogDevices(): Promise<CatalogDevicesResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices`);
  return parseJsonResponse<CatalogDevicesResponse>(response, '获取设备能力表');
}

export async function fetchDeletedCatalogDevices(): Promise<CatalogDevicesResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices/deleted`);
  return parseJsonResponse<CatalogDevicesResponse>(response, '获取已删除设备');
}

export async function createCatalogDevice(draft: CatalogDeviceDraft): Promise<CatalogDevice> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(draft),
  });
  return (await parseJsonResponse<{item: CatalogDevice}>(response, '新增设备')).item;
}

export async function updateCatalogDevice(deviceId: number, draft: CatalogDeviceDraft): Promise<CatalogDevice> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices/${encodeURIComponent(deviceId)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(draft),
  });
  return (await parseJsonResponse<{item: CatalogDevice}>(response, '保存设备')).item;
}

export async function deleteCatalogDevice(deviceId: number): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices/${encodeURIComponent(deviceId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`删除设备失败，HTTP ${response.status}`);
  }
}

export async function restoreCatalogDevice(deviceId: number): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/devices/${encodeURIComponent(deviceId)}/restore`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`恢复设备失败，HTTP ${response.status}`);
  }
}

export async function downloadAgentSourceFile(runId: string): Promise<Blob> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/source-file`);
  if (!response.ok) {
    throw new Error(`下载源文件失败，HTTP ${response.status}`);
  }
  return await response.blob();
}

export async function recalculateAgentQuotation(
  runId: string,
  quoteId: string,
  quotation: Pick<AgentQuotationItem, 'test_project_id' | 'fixed_fields' | 'special_fields'>,
  selectedDeviceCode: string | null = null,
): Promise<AgentQuotationItem> {
  const response = await fetchWithTimeout(
    `${API_BASE}/runs/${encodeURIComponent(runId)}/quotations/${encodeURIComponent(quoteId)}/recalculate`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        test_project_id: quotation.test_project_id,
        fixed_fields: quotation.fixed_fields,
        special_fields: quotation.special_fields,
        selected_device_code: selectedDeviceCode,
      }),
    },
  );
  return parseJsonResponse<AgentQuotationItem>(response, '重新筛选设备并报价');
}

export async function saveAgentQuotationSnapshot(
  runId: string,
  quoteId: string,
  quotation: Pick<AgentQuotationItem, 'test_project_id' | 'fixed_fields' | 'special_fields' | 'selected_device_code' | 'base_fee_override'>,
  selectedDeviceCode: string | null = quotation.selected_device_code,
): Promise<AgentQuotationItem> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/quotations/${encodeURIComponent(quoteId)}/snapshot`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      test_project_id: quotation.test_project_id,
      fixed_fields: quotation.fixed_fields,
        special_fields: quotation.special_fields,
        selected_device_code: selectedDeviceCode,
        base_fee_override: quotation.base_fee_override ?? null,
    }),
  });
  return parseJsonResponse<AgentQuotationItem>(response, '保存报价修改');
}

export async function setAgentQuotationBaseFeeOverride(runId: string, enabled: boolean): Promise<AgentQuotationResults> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/quotations/base-fee-override`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled}),
  });
  return parseJsonResponse<AgentQuotationResults>(response, '更新基本金设置');
}

export async function saveAgentQuotationsToHistory(runId: string): Promise<HistoricalQuotationSaveResult> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/history-quotations`, {
    method: 'POST',
  });
  return parseJsonResponse<HistoricalQuotationSaveResult>(response, '保存至历史报价库');
}

export async function exportAgentQuotation(runId: string, quoteId = ''): Promise<Blob> {
  const query = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : '';
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/export${query}`, {method: 'POST'});
  if (!response.ok) {
    throw new Error(`导出报价单失败，HTTP ${response.status}`);
  }
  return await response.blob();
}

export async function fetchRun(run_id: string): Promise<RunState> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(run_id)}`);
  return parseJsonResponse<RunState>(response, '获取运行状态');
}

export async function fetchRunHistory(): Promise<RunHistoryResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/runs`);
  return parseJsonResponse<RunHistoryResponse>(response, '获取报价历史');
}

export async function exportRun(runId: string, quoteId = ''): Promise<Blob> {
  const params = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : '';
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/export${params}`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`导出失败，HTTP ${response.status}`);
  }
  return await response.blob();
}

export async function resumeRun(runId: string, request: ResumeRequest): Promise<RunState> {

  const response = await fetchWithTimeout(
    `${API_BASE}/runs/${encodeURIComponent(runId)}/resume`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(request),
    },
    RUN_REQUEST_TIMEOUT_MS,
  );
  return parseJsonResponse<RunState>(response, '重新报价');
}

export async function updateBatchQuoteVisibility(runId: string, quoteId: string, isDeleted: boolean): Promise<RunState> {
  const response = await fetchWithTimeout(
    `${API_BASE}/runs/${encodeURIComponent(runId)}/batch-quotes/${encodeURIComponent(quoteId)}`,
    {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({is_deleted: isDeleted}),
    },
  );
  return parseJsonResponse<RunState>(response, isDeleted ? '删除子报价' : '恢复子报价');
}

export async function fetchTestTypes(): Promise<TestTypeCatalogResponse> {
  const response = await fetchWithTimeout(`${API_BASE}/catalog/test-types`);
  return parseJsonResponse<TestTypeCatalogResponse>(response, '获取标准试验类型目录');
}

export async function updateTestTypeAliases(testTypeId: number, aliases: string[]): Promise<TestTypeAliasesUpdateResponse> {
  const response = await fetchWithTimeout(
    `${API_BASE}/catalog/test-types/${encodeURIComponent(testTypeId)}/aliases`,
    {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({aliases}),
    },
  );
  return parseJsonResponse<TestTypeAliasesUpdateResponse>(response, '更新标准试验类型同义词');
}

export function buildArtifactUrl(runId: string, artifactPath: string): string {
  const encodedPath = artifactPath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  return `${API_BASE}/runs/${encodeURIComponent(runId)}/artifacts/${encodedPath}`;
}
