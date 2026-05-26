/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Download, HelpCircle, KeyRound, LayoutDashboard, Loader2, LogOut, Settings, X} from 'lucide-react';
import {API_BASE, buildArtifactUrl, createRun, createRunFromText, exportRun, fetchAuthSession, fetchRun, loginWithPassword, logout, toErrorMessage} from './api';
import logoUrl from './assets/logo_cut.png';
import smallLogoUrl from './assets/small_logo.png';
import {EquipmentTables} from './components/EquipmentTables';
import {StatusDashboard} from './components/StatusDashboard';
import {StructuredReportGrid} from './components/StructuredReportGrid';
import {TestTypeAliasManager} from './components/TestTypeAliasManager';
import {UploadSection} from './components/UploadSection';
import type {BatchQuoteItem, FormStageSnapshot, RunState, UploadedDocument} from './types';
import type {QuoteMode} from './api';

type View = 'upload' | 'dashboard' | 'settings';
type PreviewKind = 'image' | 'pdf';

type PreviewDocument = {
  fileName: string;
  kind: PreviewKind;
  url: string;
};

export default function App() {
  const [authChecking, setAuthChecking] = React.useState(true);
  const [authenticated, setAuthenticated] = React.useState(false);
  const [authSubmitting, setAuthSubmitting] = React.useState(false);
  const [authError, setAuthError] = React.useState('');
  const [view, setView] = React.useState<View>('upload');
  const [runState, setRunState] = React.useState<RunState | null>(null);
  const [activeStageId, setActiveStageId] = React.useState('');
  const [activeQuoteId, setActiveQuoteId] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [stageDialogOpen, setStageDialogOpen] = React.useState(false);
  const [previewDocument, setPreviewDocument] = React.useState<PreviewDocument | null>(null);

  React.useEffect(() => {
    let mounted = true;
    async function checkSession() {
      try {
        const session = await fetchAuthSession();
        if (mounted) {
          setAuthenticated(session.authenticated);
        }
      } catch {
        if (mounted) {
          setAuthenticated(false);
        }
      } finally {
        if (mounted) {
          setAuthChecking(false);
        }
      }
    }
    void checkSession();
    return () => {
      mounted = false;
    };
  }, []);

  React.useEffect(() => {
    function handleAuthExpired() {
      setAuthenticated(false);
      setRunState(null);
      setView('upload');
      setError('');
      setAuthError('登录已过期，请重新输入密码。');
    }
    window.addEventListener('autoquote:auth-expired', handleAuthExpired);
    return () => window.removeEventListener('autoquote:auth-expired', handleAuthExpired);
  }, []);

  const activeBatchQuote: BatchQuoteItem | undefined = React.useMemo(() => {
    if (!runState) {
      return undefined;
    }
    if (runState.quote_mode !== 'batch') {
      return undefined;
    }
    return runState.batch_quotes.find((quote) => quote.quote_id === activeQuoteId) ?? runState.batch_quotes[0];
  }, [activeQuoteId, runState]);

  const visibleStages = activeBatchQuote?.form_stages ?? runState?.form_stages ?? [];
  const canExport = React.useMemo(() => {
    if (!runState) {
      return false;
    }
    return runState.final_form_items.some((row) => row.stage_status === 'quoted' && row.total_price != null);
  }, [runState]);

  const activeStage: FormStageSnapshot | undefined = React.useMemo(() => {
    return visibleStages.find((stage) => stage.stage_id === activeStageId) ?? visibleStages.at(-1);
  }, [activeStageId, visibleStages]);

  React.useEffect(() => {
    if (!previewDocument && !stageDialogOpen) {
      return undefined;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setPreviewDocument(null);
        setStageDialogOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [previewDocument, stageDialogOpen]);

  function syncActivePointers(next: RunState, preferredStageId = activeStageId, preferredQuoteId = activeQuoteId) {
    const nextQuote = next.quote_mode === 'batch'
      ? next.batch_quotes.find((quote) => quote.quote_id === preferredQuoteId) ?? next.batch_quotes[0]
      : undefined;
    const stages = nextQuote?.form_stages ?? next.form_stages;
    setActiveQuoteId(nextQuote?.quote_id ?? '');
    setActiveStageId(stages.some((stage) => stage.stage_id === preferredStageId) ? preferredStageId : stages.at(-1)?.stage_id ?? next.current_stage);
  }

  async function handleStart(files: File[], quoteMode: QuoteMode) {
    if (files.length === 0) {
      setError('请先选择至少一个 Word、Excel、PDF 或图片文件。');
      return;
    }
    if (quoteMode === 'batch' && (files.length !== 1 || !files[0].name.toLowerCase().endsWith('.xlsx'))) {
      setError('批量报价只支持上传 1 个 Excel（.xlsx）文件。');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const next = await createRun(files, quoteMode);
      setRunState(next);
      syncActivePointers(next, '', '');
      setView('dashboard');
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `${API_BASE}/runs 无法创建运行`));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStartFromText(text: string) {
    if (!text.trim()) {
      setError('请先输入或粘贴报价需求文本。');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const next = await createRunFromText(text);
      setRunState(next);
      syncActivePointers(next, '', '');
      setView('dashboard');
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `${API_BASE}/runs/text 无法创建运行`));
    } finally {
      setSubmitting(false);
    }
  }

  async function refreshRun() {
    if (!runState || refreshing) {
      return;
    }
    setRefreshing(true);
    setError('');
    try {
      const next = await fetchRun(runState.run_id);
      setRunState(next);
      syncActivePointers(next);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法刷新当前运行状态'));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleExport() {
    if (!runState || submitting) {
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const blob = await exportRun(runState.run_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `报价单_${runState.run_id}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      await refreshRun();
    } catch (err) {
      setError(toErrorMessage(err, '导出报价单失败'));
    } finally {
      setSubmitting(false);
    }
  }

  function handleRunUpdated(next: RunState) {
    setRunState(next);
    syncActivePointers(next);
  }

  function artifactUrl(path: string) {
    return runState ? buildArtifactUrl(runState.run_id, path) : '#';
  }

  function handleUploadedDocumentClick(event: React.MouseEvent<HTMLAnchorElement>, document: UploadedDocument) {
    if (!runState) {
      return;
    }
    event.preventDefault();
    const url = buildArtifactUrl(runState.run_id, document.stored_path);
    const action = getDocumentAction(document);
    if (action === 'download') {
      triggerDownload(url, document.file_name);
      return;
    }
    setPreviewDocument({
      fileName: document.file_name,
      kind: action,
      url,
    });
  }

  async function handleLogin(password: string) {
    setAuthSubmitting(true);
    setAuthError('');
    try {
      await loginWithPassword(password);
      setAuthenticated(true);
    } catch (err) {
      setAuthError(toErrorMessage(err, '密码验证失败'));
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function handleLogout() {
    setAuthSubmitting(true);
    setAuthError('');
    try {
      await logout();
    } finally {
      setAuthenticated(false);
      setRunState(null);
      setView('upload');
      setAuthSubmitting(false);
    }
  }

  if (authChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        正在检查授权状态...
      </div>
    );
  }

  if (!authenticated) {
    return <LoginScreen error={authError} isSubmitting={authSubmitting} onSubmit={(password) => void handleLogin(password)} />;
  }

  return (
    <div className="min-h-screen flex text-slate-900">
      <aside className="w-16 md:w-20 bg-slate-900 flex flex-col items-center py-8 gap-8 shrink-0">
        <nav className="flex flex-col gap-6 text-slate-500">
          <NavItem
            imageSrc={smallLogoUrl}
            active={view === 'upload'}
            onClick={() => {
              setView('upload');
              setError('');
            }}
          />
          <NavItem icon={LayoutDashboard} active={view === 'dashboard'} onClick={() => runState && setView('dashboard')} disabled={!runState} />
          <NavItem icon={Settings} active={view === 'settings'} onClick={() => setView('settings')} />
        </nav>
        <div className="mt-auto">
          <NavItem icon={HelpCircle} />
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <header className="relative h-16 border-b border-slate-200/60 bg-white/70 backdrop-blur-md sticky top-0 z-20 px-4 md:px-8 flex items-center justify-between">
          <div className="absolute bottom-0 left-4 top-1 flex items-end md:left-8">
            <img className="h-full w-52 object-contain object-left-bottom" src={logoUrl} alt="" />
          </div>
          <h1 className="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-center text-lg font-bold text-slate-800">
            <span>
              千验智能报价系统
            </span>
          </h1>
          <div className="relative z-10 ml-auto flex items-center gap-3">
            {view === 'dashboard' && runState ? (
              <>
                <button type="button" onClick={() => void handleExport()} disabled={submitting || !canExport} className="btn-secondary text-xs flex items-center gap-1.5 disabled:opacity-50">
                  <Download className="w-3.5 h-3.5" />
                  导出报价单
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setView('upload');
                    setError('');
                  }}
                  className="btn-secondary text-xs"
                >
                  返回重新上传
                </button>
              </>
            ) : null}
            <button
              type="button"
              onClick={() => void handleLogout()}
              disabled={authSubmitting}
              className="btn-secondary text-xs inline-flex items-center gap-1.5"
              aria-label="退出登录"
            >
              <LogOut className="h-3.5 w-3.5" />
              退出
            </button>
          </div>
        </header>

        <div className="p-4 md:p-8">
          {view === 'upload' ? (
            <UploadSection
              error={error}
              isSubmitting={submitting}
              onStart={(files, quoteMode) => void handleStart(files, quoteMode)}
              onStartFromText={(text) => void handleStartFromText(text)}
            />
          ) : view === 'settings' ? (
            <TestTypeAliasManager />
          ) : runState ? (
            <div className="max-w-screen-2xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
              {error ? <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
              <StatusDashboard
                runState={runState}
                onDocumentOpen={handleUploadedDocumentClick}
                onRefresh={() => void refreshRun()}
                artifactUrl={artifactUrl}
                isRefreshing={refreshing}
              />
              {runState.quote_mode === 'batch' ? (
                <BatchQuoteSwitcher
                  quotes={runState.batch_quotes}
                  activeQuoteId={activeBatchQuote?.quote_id ?? ''}
                  onSelect={(quote) => {
                    setActiveQuoteId(quote.quote_id);
                    setActiveStageId(quote.form_stages.at(-1)?.stage_id ?? '');
                  }}
                />
              ) : null}
              <div className="space-y-4">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
                  <h2 className="text-2xl font-bold text-slate-800">结构化报价报表</h2>
                  <p className="text-slate-400 text-sm font-medium">STRUCTURED QUOTE REPORT</p>
                </div>
                <StructuredReportGrid activeStage={activeStage} runState={runState} onUpdated={handleRunUpdated} />
                <EquipmentTables activeStage={activeStage} runState={runState} onUpdated={handleRunUpdated} />
              </div>
            </div>
          ) : (
            <div className="glass-panel mx-auto mt-16 max-w-xl p-8 text-center text-slate-500">
              当前没有运行数据，请返回上传页创建运行。
            </div>
          )}
        </div>
      </main>

      {stageDialogOpen && runState ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="presentation" onClick={() => setStageDialogOpen(false)}>
          <div
            className="w-full max-w-3xl rounded-xl border border-slate-200 bg-white shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label="阶段切换"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-4">
              <div>
                <div className="text-base font-bold text-slate-800">阶段切换</div>
                <div className="mt-1 text-xs text-slate-400">表头不变，只切换结构化报价表在不同步骤的填写快照。</div>
              </div>
              <button type="button" className="btn-secondary text-xs inline-flex items-center gap-1" onClick={() => setStageDialogOpen(false)}>
                <X size={14} />
                关闭
              </button>
            </div>
            <div className="p-4">
              <div className="flex flex-wrap gap-2">
                {visibleStages.map((stage) => (
                  <button
                    key={stage.stage_id}
                    type="button"
                    className={`rounded-full border px-3 py-1.5 text-xs font-bold transition-colors ${stage.stage_id === activeStage?.stage_id ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-500 hover:border-indigo-200'}`}
                    onClick={() => {
                      setActiveStageId(stage.stage_id);
                      setStageDialogOpen(false);
                    }}
                  >
                    {stage.label}
                  </button>
                ))}
              </div>
              {activeStage && activeStage.notes.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {activeStage.notes.map((note, index) => (
                    <span key={`${activeStage.stage_id}-${index}`} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-500">
                      {note}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {previewDocument ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4" role="presentation" onClick={() => setPreviewDocument(null)}>
          <div
            className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label={previewDocument.fileName}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-4 border-b border-slate-100 p-4">
              <div className="min-w-0 truncate text-sm font-bold text-slate-800">{previewDocument.fileName}</div>
              <div className="flex items-center gap-2">
                <a className="btn-secondary text-xs" href={previewDocument.url} download={previewDocument.fileName}>下载</a>
                <button type="button" className="btn-secondary text-xs" onClick={() => setPreviewDocument(null)}>关闭</button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto bg-slate-50 p-4">
              {previewDocument.kind === 'image' ? (
                <img className="mx-auto max-h-[75vh] max-w-full rounded-lg object-contain" src={previewDocument.url} alt={previewDocument.fileName} />
              ) : (
                <iframe className="h-[75vh] w-full rounded-lg border border-slate-200 bg-white" src={previewDocument.url} title={previewDocument.fileName} />
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function BatchQuoteSwitcher({
  quotes,
  activeQuoteId,
  onSelect,
}: {
  quotes: BatchQuoteItem[];
  activeQuoteId: string;
  onSelect: (quote: BatchQuoteItem) => void;
}) {
  if (quotes.length === 0) {
    return null;
  }
  return (
    <div className="glass-panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-800">批量报价</h2>
          <p className="mt-0.5 text-xs text-slate-400">切换查看每个子报价的结构化表格和设备匹配结果。</p>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500">
          {quotes.length} 项
        </span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {quotes.map((quote, index) => {
          const active = quote.quote_id === activeQuoteId;
          const quotedCount = quote.final_form_items.filter((row) => row.stage_status === 'quoted' && row.total_price != null).length;
          return (
            <button
              key={quote.quote_id}
              type="button"
              onClick={() => onSelect(quote)}
              className={`min-w-56 rounded-lg border px-3 py-2 text-left transition-colors ${active ? 'border-indigo-200 bg-indigo-50 text-indigo-800' : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-bold">{quote.title || `子报价 ${index + 1}`}</span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${getQuoteStatusClass(quote.status)}`}>
                  {quote.status.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="mt-1 truncate text-xs opacity-75">{quote.source_summary || quote.quote_id}</div>
              <div className="mt-1 text-xs opacity-75">已报价 {quotedCount} / {quote.final_form_items.length}</div>
            </button>
          );
        })}
      </div>
      {quotes.some((quote) => quote.errors.length > 0) ? (
        <div className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
          {quotes.filter((quote) => quote.errors.length > 0).map((quote) => `${quote.title || quote.quote_id}: ${quote.errors.join('；')}`).join('；')}
        </div>
      ) : null}
    </div>
  );
}

function getQuoteStatusClass(status: BatchQuoteItem['status']): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-100 text-emerald-700';
    case 'waiting_manual_input':
      return 'bg-amber-100 text-amber-700';
    case 'failed':
      return 'bg-red-100 text-red-700';
    default:
      return 'bg-blue-100 text-blue-700';
  }
}

function LoginScreen({
  error,
  isSubmitting,
  onSubmit,
}: {
  error: string;
  isSubmitting: boolean;
  onSubmit: (password: string) => void;
}) {
  const [password, setPassword] = React.useState('');

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password.trim() || isSubmitting) {
      return;
    }
    onSubmit(password);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-8 text-slate-900">
      <form className="glass-panel w-full max-w-md p-8" onSubmit={handleSubmit}>
        <div className="mb-7 text-center">
          <img className="mx-auto mb-4 h-28 w-56 object-contain" src={logoUrl} alt="" />
          <h1 className="text-xl font-bold text-slate-800">千验智能报价系统</h1>
          <p className="mt-2 text-sm text-slate-500">请输入授权密码后继续使用。</p>
        </div>

        <label className="block text-sm font-semibold text-slate-700" htmlFor="auth-password">
          授权密码
        </label>
        <div className="mt-2 flex items-center rounded-xl border border-slate-200 bg-white px-3 focus-within:border-indigo-300 focus-within:ring-4 focus-within:ring-indigo-50">
          <KeyRound className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            id="auth-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="h-11 min-w-0 flex-1 bg-transparent px-3 text-sm font-medium text-slate-800 outline-none"
            autoComplete="current-password"
            autoFocus
          />
        </div>

        {error ? <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

        <button
          type="submit"
          disabled={!password.trim() || isSubmitting}
          className="btn-primary mt-6 flex w-full items-center justify-center gap-2 disabled:opacity-50 disabled:shadow-none"
        >
          {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
          {isSubmitting ? '验证中...' : '解锁使用'}
        </button>
      </form>
    </main>
  );
}

function NavItem({
  icon: Icon,
  imageSrc,
  active,
  disabled,
  onClick,
}: {
  icon?: React.ComponentType<{size?: number}>;
  imageSrc?: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`p-3 rounded-xl transition-all disabled:cursor-not-allowed disabled:opacity-30 ${active ? 'bg-white text-slate-900 shadow-md shadow-slate-950/20 scale-110' : 'hover:bg-slate-800 hover:text-slate-300'}`}
    >
      {imageSrc ? <img className="h-5 w-5 object-contain" src={imageSrc} alt="" /> : Icon ? <Icon size={20} /> : null}
    </button>
  );
}

function getFileExtension(fileName: string): string {
  const parts = fileName.toLowerCase().split('.');
  return parts.length > 1 ? parts.at(-1) ?? '' : '';
}

function isImageDocument(document: UploadedDocument): boolean {
  if (document.media_type.toLowerCase().startsWith('image/')) {
    return true;
  }
  return ['png', 'jpg', 'jpeg', 'bmp', 'webp', 'gif'].includes(getFileExtension(document.file_name));
}

function isPdfDocument(document: UploadedDocument): boolean {
  return document.media_type.toLowerCase() === 'application/pdf' || getFileExtension(document.file_name) === 'pdf';
}

function getDocumentAction(document: UploadedDocument): PreviewKind | 'download' {
  if (isImageDocument(document)) {
    return 'image';
  }
  if (isPdfDocument(document)) {
    return 'pdf';
  }
  return 'download';
}

function triggerDownload(url: string, fileName: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
}
