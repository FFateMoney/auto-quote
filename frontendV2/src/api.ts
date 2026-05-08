import type {ResumeRequest, RunState, TestTypeAliasesUpdateResponse, TestTypeCatalogResponse} from './types';

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

export async function createRun(files: File[]): Promise<RunState> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const response = await fetchWithTimeout(
    `${API_BASE}/runs`,
    {
      method: 'POST',
      body: formData,
    },
    RUN_REQUEST_TIMEOUT_MS,
  );
  return parseJsonResponse<RunState>(response, '创建运行');
}

export async function createRunFromText(text: string): Promise<RunState> {
  const response = await fetchWithTimeout(
    `${API_BASE}/runs/text`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text}),
    },
    RUN_REQUEST_TIMEOUT_MS,
  );
  return parseJsonResponse<RunState>(response, '创建文本运行');
}

export async function fetchRun(run_id: string): Promise<RunState> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(run_id)}`);
  return parseJsonResponse<RunState>(response, '获取运行状态');
}

export async function exportRun(runId: string): Promise<Blob> {
  const response = await fetchWithTimeout(`${API_BASE}/runs/${encodeURIComponent(runId)}/export`, {
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
