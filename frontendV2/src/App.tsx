/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Download, HelpCircle, KeyRound, LayoutDashboard, Loader2, LogOut, RotateCcw, Save, Settings, Trash2, X} from 'lucide-react';
import {API_BASE, buildArtifactUrl, createRun, downloadAgentSourceFile, exportAgentQuotation, exportRun, fetchAgentQuotationResults, fetchAgentRun, fetchAuthSession, fetchRun, loginWithPassword, logout, saveAgentQuotationSnapshot, saveAgentQuotationsToHistory, setAgentQuotationBaseFeeOverride, toErrorMessage, updateBatchQuoteVisibility} from './api';
import logoUrl from './assets/logo_cut.png';
import smallLogoUrl from './assets/small_logo.png';
import {EquipmentTables} from './components/EquipmentTables';
import {DatabaseManager} from './components/DatabaseManager';
import {StatusDashboard} from './components/StatusDashboard';
import {StructuredReportGrid} from './components/StructuredReportGrid';
import {UploadSection} from './components/UploadSection';
import type {BatchQuoteItem, FormStageSnapshot, RunState, UploadedDocument} from './types';
import type {AgentQuotationItem, AgentQuotationResults, AgentRunSnapshot} from './api';

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
  const [agentRun, setAgentRun] = React.useState<AgentRunSnapshot | null>(null);
  const [agentQuotationResults, setAgentQuotationResults] = React.useState<AgentQuotationResults | null>(null);
  const [agentResultsOpen, setAgentResultsOpen] = React.useState(false);
  const [agentResultsLoading, setAgentResultsLoading] = React.useState(false);
  const [agentResultsError, setAgentResultsError] = React.useState('');
  const [agentResultsReloadKey, setAgentResultsReloadKey] = React.useState(0);
  const [agentSourceDownloading, setAgentSourceDownloading] = React.useState(false);
  const [agentExporting, setAgentExporting] = React.useState(false);
  const [agentHistorySaving, setAgentHistorySaving] = React.useState(false);
  const [agentBaseFeeUpdating, setAgentBaseFeeUpdating] = React.useState(false);
  const [agentHistorySaveMessage, setAgentHistorySaveMessage] = React.useState('');
  const [agentRequoting, setAgentRequoting] = React.useState(false);
  const [activeAgentQuoteId, setActiveAgentQuoteId] = React.useState('');
  const [activeStageId, setActiveStageId] = React.useState('');
  const [activeQuoteId, setActiveQuoteId] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [stageDialogOpen, setStageDialogOpen] = React.useState(false);
  const [previewDocument, setPreviewDocument] = React.useState<PreviewDocument | null>(null);
  const [quoteVisibilityUpdating, setQuoteVisibilityUpdating] = React.useState('');

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
    if (!agentRun || agentRun.status === 'submitted' || agentRun.status === 'agent_failed' || agentRun.status === 'submission_rejected') {
      return;
    }
    const timer = window.setInterval(() => {
      void fetchAgentRun(agentRun.run_id).then(setAgentRun).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [agentRun]);

  React.useEffect(() => {
    if (!agentRun || agentRun.status !== 'submitted') {
      return;
    }
    let cancelled = false;
    setAgentResultsLoading(true);
    setAgentResultsError('');
    void fetchAgentQuotationResults(agentRun.run_id)
      .then((results) => {
        if (cancelled) {
          return;
        }
        setAgentQuotationResults(results);
        setActiveAgentQuoteId((current) => results.items.some((item) => item.quote_id === current) ? current : results.items[0]?.quote_id ?? '');
        setAgentResultsOpen(true);
      })
      .catch((fetchError) => {
        if (!cancelled) {
          setAgentResultsError(toErrorMessage(fetchError, '无法获取报价结果'));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAgentResultsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [agentRun?.run_id, agentRun?.status, agentResultsReloadKey]);

  React.useEffect(() => {
    function handleAuthExpired() {
      setAuthenticated(false);
      setRunState(null);
      setAgentRun(null);
      setAgentQuotationResults(null);
      setAgentResultsOpen(false);
      setAgentResultsError('');
      setAgentHistorySaveMessage('');
      setActiveAgentQuoteId('');
      setView('upload');
      setError('');
      setAuthError('登录已过期，请重新输入密码。');
    }
    window.addEventListener('autoquote:auth-expired', handleAuthExpired);
    return () => window.removeEventListener('autoquote:auth-expired', handleAuthExpired);
  }, []);

  const visibleBatchQuotes = React.useMemo(() => {
    return runState?.quote_mode === 'batch' ? runState.batch_quotes.filter((quote) => !quote.is_deleted) : [];
  }, [runState]);

  const activeBatchQuote: BatchQuoteItem | undefined = React.useMemo(() => {
    if (!runState) {
      return undefined;
    }
    if (runState.quote_mode !== 'batch') {
      return undefined;
    }
    return visibleBatchQuotes.find((quote) => quote.quote_id === activeQuoteId) ?? visibleBatchQuotes[0];
  }, [activeQuoteId, runState, visibleBatchQuotes]);

  const visibleStages = runState?.quote_mode === 'batch'
    ? activeBatchQuote?.form_stages ?? []
    : runState?.form_stages ?? [];
  const displayRunState = React.useMemo<RunState | null>(() => {
    if (!runState) {
      return null;
    }
    if (runState.quote_mode !== 'batch' || !activeBatchQuote) {
      return runState;
    }
    return {
      ...runState,
      form_stages: activeBatchQuote.form_stages,
      final_form_items: activeBatchQuote.final_form_items,
    };
  }, [activeBatchQuote, runState]);
  const canExport = React.useMemo(() => {
    if (!runState) {
      return false;
    }
    return runState.final_form_items.some((row) => row.stage_status === 'quoted' && row.total_price != null);
  }, [runState]);
  const canExportActiveQuote = React.useMemo(() => {
    if (!activeBatchQuote) {
      return false;
    }
    return activeBatchQuote.final_form_items.some((row) => row.stage_status === 'quoted' && row.total_price != null);
  }, [activeBatchQuote]);

  const activeStage: FormStageSnapshot | undefined = React.useMemo(() => {
    return visibleStages.find((stage) => stage.stage_id === activeStageId) ?? visibleStages.at(-1);
  }, [activeStageId, visibleStages]);

  const activeAgentQuote = React.useMemo(() => {
    const quotations = agentQuotationResults?.items ?? [];
    return quotations.find((item) => item.quote_id === activeAgentQuoteId) ?? quotations[0];
  }, [activeAgentQuoteId, agentQuotationResults]);

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
    const nextVisibleQuotes = next.quote_mode === 'batch' ? next.batch_quotes.filter((quote) => !quote.is_deleted) : [];
    const nextQuote = next.quote_mode === 'batch'
      ? nextVisibleQuotes.find((quote) => quote.quote_id === preferredQuoteId) ?? nextVisibleQuotes[0]
      : undefined;
    const stages = next.quote_mode === 'batch' ? nextQuote?.form_stages ?? [] : next.form_stages;
    setActiveQuoteId(nextQuote?.quote_id ?? '');
    setActiveStageId(stages.some((stage) => stage.stage_id === preferredStageId) ? preferredStageId : stages.at(-1)?.stage_id ?? next.current_stage);
  }

  async function handleStart(files: File[]) {
    if (files.length === 0) {
      setError('请先提供一个报价需求文档或粘贴报价需求文本。');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const next = await createRun(files);
      setRunState(null);
      setAgentRun(next);
      setAgentQuotationResults(null);
      setAgentResultsOpen(false);
      setAgentResultsError('');
      setAgentHistorySaveMessage('');
      setActiveAgentQuoteId('');
      setView('dashboard');
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, `${API_BASE}/runs 无法创建运行`));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLoadHistory(runId: string) {
    if (!runId || submitting) {
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const next = await fetchAgentRun(runId);
      setRunState(null);
      setAgentRun(next);
      setAgentQuotationResults(null);
      setAgentResultsOpen(false);
      setAgentResultsError('');
      setActiveAgentQuoteId('');
      setView('dashboard');
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法加载历史报价'));
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

  async function refreshAgentRun() {
    if (!agentRun || refreshing) {
      return;
    }
    setRefreshing(true);
    setError('');
    try {
      setAgentRun(await fetchAgentRun(agentRun.run_id));
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法刷新当前运行状态'));
    } finally {
      setRefreshing(false);
    }
  }

  function replaceAgentQuotation(nextQuotation: AgentQuotationItem) {
    setAgentQuotationResults((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        items: current.items.map((quotation) => quotation.quote_id === nextQuotation.quote_id ? nextQuotation : quotation),
      };
    });
  }

  async function saveAgentQuotation(
    nextQuotation: Pick<AgentQuotationItem, 'quote_id' | 'test_project_id' | 'fixed_fields' | 'special_fields' | 'selected_device_code' | 'base_fee_override'>,
    selectedDeviceCode: string | null = null,
  ) {
    if (!agentRun || agentRequoting) {
      return;
    }
    setAgentRequoting(true);
    setError('');
    try {
      const saved = await saveAgentQuotationSnapshot(
        agentRun.run_id,
        nextQuotation.quote_id,
        nextQuotation,
        selectedDeviceCode,
      );
      replaceAgentQuotation(saved);
      setAgentHistorySaveMessage('');
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法保存报价修改'));
    } finally {
      setAgentRequoting(false);
    }
  }

  async function handleAgentQuotationRecalculation(selectedDeviceCode: string | null = null) {
    if (!agentRun || !activeAgentQuote || agentRequoting) {
      return;
    }
    await saveAgentQuotation(activeAgentQuote, selectedDeviceCode);
  }

  async function handleAgentExport(quoteId = '') {
    if (!agentRun || agentExporting) {
      return;
    }
    setAgentExporting(true);
    setError('');
    try {
      const blob = await exportAgentQuotation(agentRun.run_id, quoteId);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = quoteId ? `报价单_${agentRun.run_id}_${quoteId}.docx` : `报价单_${agentRun.run_id}.docx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '导出报价单失败'));
    } finally {
      setAgentExporting(false);
    }
  }

  async function handleSaveAgentQuotationsToHistory() {
    if (!agentRun || !agentQuotationResults || agentHistorySaving) {
      return;
    }
    setAgentHistorySaving(true);
    setAgentHistorySaveMessage('');
    setError('');
    try {
      const result = await saveAgentQuotationsToHistory(agentRun.run_id);
      setAgentHistorySaveMessage(`已保存 ${result.saved_count} 项到历史报价库。`);
    } catch (saveError) {
      setError(toErrorMessage(saveError, '无法保存至历史报价库'));
    } finally {
      setAgentHistorySaving(false);
    }
  }

  async function handleSetAgentQuotationBaseFeeOverride(enabled: boolean) {
    if (!agentRun || !agentQuotationResults || agentBaseFeeUpdating || agentRequoting) {
      return;
    }
    setAgentBaseFeeUpdating(true);
    setError('');
    try {
      const results = await setAgentQuotationBaseFeeOverride(agentRun.run_id, enabled);
      setAgentQuotationResults(results);
      setAgentHistorySaveMessage('');
    } catch (saveError) {
      setError(toErrorMessage(saveError, '更新基本金设置失败'));
    } finally {
      setAgentBaseFeeUpdating(false);
    }
  }

  async function handleAgentSourceDownload() {
    if (!agentRun || agentSourceDownloading) {
      return;
    }
    setAgentSourceDownloading(true);
    setError('');
    try {
      const blob = await downloadAgentSourceFile(agentRun.run_id);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = agentRun.uploaded_file;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, '无法下载源文件'));
    } finally {
      setAgentSourceDownloading(false);
    }
  }

  async function handleExport(quoteId = '') {
    if (!runState || submitting) {
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const blob = await exportRun(runState.run_id, quoteId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = quoteId ? `报价单_${runState.run_id}_${quoteId}.docx` : `报价单_${runState.run_id}.docx`;
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

  async function handleBatchQuoteVisibility(quote: BatchQuoteItem, isDeleted: boolean) {
    if (!runState || quoteVisibilityUpdating) {
      return;
    }
    setQuoteVisibilityUpdating(quote.quote_id);
    setError('');
    try {
      const next = await updateBatchQuoteVisibility(runState.run_id, quote.quote_id, isDeleted);
      setRunState(next);
      syncActivePointers(next, activeStageId, activeQuoteId === quote.quote_id && isDeleted ? '' : activeQuoteId);
    } catch (fetchError) {
      setError(toErrorMessage(fetchError, isDeleted ? '删除子报价失败' : '恢复子报价失败'));
    } finally {
      setQuoteVisibilityUpdating('');
    }
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
      setAgentRun(null);
      setAgentQuotationResults(null);
      setAgentResultsOpen(false);
      setActiveAgentQuoteId('');
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
          <NavItem icon={LayoutDashboard} active={view === 'dashboard'} onClick={() => (runState || agentRun) && setView('dashboard')} disabled={!runState && !agentRun} />
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
            {view === 'dashboard' && (runState || agentRun) ? (
              <>
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
              onStart={(files) => void handleStart(files)}
              onLoadHistory={(runId) => void handleLoadHistory(runId)}
            />
          ) : view === 'settings' ? (
            <DatabaseManager />
          ) : agentRun ? (
            <AgentRunDashboard
              run={agentRun}
              error={error}
              refreshing={refreshing}
              onRefresh={() => void refreshAgentRun()}
              quotationResults={agentQuotationResults}
              quotationResultsOpen={agentResultsOpen}
              quotationResultsLoading={agentResultsLoading}
              quotationResultsError={agentResultsError}
              onReloadQuotationResults={() => setAgentResultsReloadKey((current) => current + 1)}
              activeQuotation={activeAgentQuote}
              activeQuotationId={activeAgentQuoteId}
              onSelectQuotation={setActiveAgentQuoteId}
              onQuotationUpdated={saveAgentQuotation}
              onRecalculateQuotation={(deviceCode) => void handleAgentQuotationRecalculation(deviceCode)}
              requoting={agentRequoting}
              onDownloadSource={() => void handleAgentSourceDownload()}
              sourceDownloading={agentSourceDownloading}
              onExportAll={() => void handleAgentExport()}
              onExportSingle={() => activeAgentQuote && void handleAgentExport(activeAgentQuote.quote_id)}
              exporting={agentExporting}
              onSaveToHistory={() => void handleSaveAgentQuotationsToHistory()}
              historySaving={agentHistorySaving}
              historySaveMessage={agentHistorySaveMessage}
              onSetBaseFeeZero={(enabled) => void handleSetAgentQuotationBaseFeeOverride(enabled)}
              baseFeeUpdating={agentBaseFeeUpdating}
            />
          ) : runState && displayRunState ? (
            <div className="max-w-screen-2xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
              {error ? <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
              <StatusDashboard
                runState={runState}
                onDocumentOpen={handleUploadedDocumentClick}
                onExportAll={() => void handleExport()}
                onExportSingle={() => activeBatchQuote && void handleExport(activeBatchQuote.quote_id)}
                onRefresh={() => void refreshRun()}
                artifactUrl={artifactUrl}
                canExportAll={canExport}
                canExportSingle={canExportActiveQuote}
                isExporting={submitting}
                isRefreshing={refreshing}
              />
              {runState.quote_mode === 'batch' ? (
                <BatchQuoteSwitcher
                  quotes={runState.batch_quotes}
                  activeQuoteId={activeBatchQuote?.quote_id ?? ''}
                  updatingQuoteId={quoteVisibilityUpdating}
                  onSelect={(quote) => {
                    setActiveQuoteId(quote.quote_id);
                    setActiveStageId(quote.form_stages.at(-1)?.stage_id ?? '');
                  }}
                  onDelete={(quote) => void handleBatchQuoteVisibility(quote, true)}
                  onRestore={(quote) => void handleBatchQuoteVisibility(quote, false)}
                />
              ) : null}
              <div className="space-y-4">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
                  <h2 className="text-2xl font-bold text-slate-800">
                    {runState.quote_mode === 'batch' && activeBatchQuote ? activeBatchQuote.title || '子报价' : '结构化报价报表'}
                  </h2>
                  <p className="text-slate-400 text-sm font-medium">STRUCTURED QUOTE REPORT</p>
                </div>
                <StructuredReportGrid activeStage={activeStage} runState={displayRunState} onUpdated={handleRunUpdated} />
                <EquipmentTables activeStage={activeStage} runState={displayRunState} onUpdated={handleRunUpdated} />
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
  updatingQuoteId,
  onSelect,
  onDelete,
  onRestore,
}: {
  quotes: BatchQuoteItem[];
  activeQuoteId: string;
  updatingQuoteId: string;
  onSelect: (quote: BatchQuoteItem) => void;
  onDelete: (quote: BatchQuoteItem) => void;
  onRestore: (quote: BatchQuoteItem) => void;
}) {
  const [trashOpen, setTrashOpen] = React.useState(false);
  const visibleQuotes = quotes.filter((quote) => !quote.is_deleted);
  const deletedQuotes = quotes.filter((quote) => quote.is_deleted);
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
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500">
            {visibleQuotes.length} / {quotes.length} 项
          </span>
          <button
            type="button"
            className={`inline-flex h-8 items-center gap-1 rounded-lg border px-2.5 text-xs font-bold transition-colors ${deletedQuotes.length > 0 ? 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:text-indigo-700' : 'cursor-not-allowed border-slate-100 bg-slate-50 text-slate-300'}`}
            disabled={deletedQuotes.length === 0}
            onClick={() => setTrashOpen((open) => !open)}
            title="回收站"
          >
            <Trash2 className="h-3.5 w-3.5" />
            回收站
            {deletedQuotes.length > 0 ? <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px]">{deletedQuotes.length}</span> : null}
          </button>
        </div>
      </div>
      {trashOpen && deletedQuotes.length > 0 ? (
        <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 text-xs font-bold text-slate-500">已删除报价</div>
          <div className="flex flex-wrap gap-2">
            {deletedQuotes.map((quote) => (
              <div key={quote.quote_id} className="flex max-w-sm items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs font-bold text-slate-700">{quote.title || quote.quote_id}</div>
                  <div className="truncate text-[11px] text-slate-400">{quote.source_summary || quote.quote_id}</div>
                </div>
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-1 rounded-md border border-emerald-100 bg-emerald-50 px-2 py-1 text-[11px] font-bold text-emerald-700 hover:border-emerald-200"
                  disabled={updatingQuoteId === quote.quote_id}
                  onClick={() => onRestore(quote)}
                  title="恢复报价"
                >
                  {updatingQuoteId === quote.quote_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
                  恢复
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {visibleQuotes.length === 0 ? (
        <div className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
          当前没有可见子报价，可从回收站恢复。
        </div>
      ) : null}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {visibleQuotes.map((quote, index) => {
          const active = quote.quote_id === activeQuoteId;
          const quotedCount = quote.final_form_items.filter((row) => row.stage_status === 'quoted' && row.total_price != null).length;
          return (
            <div
              key={quote.quote_id}
              className={`min-w-56 rounded-lg border transition-colors ${active ? 'border-indigo-200 bg-indigo-50 text-indigo-800' : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200'}`}
            >
              <button type="button" onClick={() => onSelect(quote)} className="block w-full px-3 pb-2 pt-2 text-left">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-bold">{quote.title || `子报价 ${index + 1}`}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${getQuoteStatusClass(quote.status)}`}>
                    {quote.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="mt-1 truncate text-xs opacity-75">{quote.source_summary || quote.quote_id}</div>
                <div className="mt-1 text-xs opacity-75">报价行 {quotedCount} / {quote.final_form_items.length}</div>
              </button>
              <div className="flex justify-end border-t border-slate-100 px-2 py-1">
                <button
                  type="button"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600"
                  disabled={updatingQuoteId === quote.quote_id}
                  onClick={() => onDelete(quote)}
                  title="删除报价"
                  aria-label={`删除 ${quote.title || quote.quote_id}`}
                >
                  {updatingQuoteId === quote.quote_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {visibleQuotes.some((quote) => quote.errors.length > 0) ? (
        <div className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
          {visibleQuotes.filter((quote) => quote.errors.length > 0).map((quote) => `${quote.title || quote.quote_id}: ${quote.errors.join('；')}`).join('；')}
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

function AgentRunDashboard({
  run,
  error,
  refreshing,
  onRefresh,
  quotationResults,
  quotationResultsOpen,
  quotationResultsLoading,
  quotationResultsError,
  onReloadQuotationResults,
  activeQuotation,
  activeQuotationId,
  onSelectQuotation,
  onQuotationUpdated,
  onRecalculateQuotation,
  requoting,
  onDownloadSource,
  sourceDownloading,
  onExportAll,
  onExportSingle,
  exporting,
  onSaveToHistory,
  historySaving,
  historySaveMessage,
  onSetBaseFeeZero,
  baseFeeUpdating,
}: {
  run: AgentRunSnapshot;
  error: string;
  refreshing: boolean;
  onRefresh: () => void;
  quotationResults: AgentQuotationResults | null;
  quotationResultsOpen: boolean;
  quotationResultsLoading: boolean;
  quotationResultsError: string;
  onReloadQuotationResults: () => void;
  activeQuotation: AgentQuotationItem | undefined;
  activeQuotationId: string;
  onSelectQuotation: (quoteId: string) => void;
  onQuotationUpdated: (quotation: AgentQuotationItem) => Promise<void>;
  onRecalculateQuotation: (deviceCode?: string | null) => void;
  requoting: boolean;
  onDownloadSource: () => void;
  sourceDownloading: boolean;
  onExportAll: () => void;
  onExportSingle: () => void;
  exporting: boolean;
  onSaveToHistory: () => void;
  historySaving: boolean;
  historySaveMessage: string;
  onSetBaseFeeZero: (enabled: boolean) => void;
  baseFeeUpdating: boolean;
}) {
  const isRunning = run.status === 'created' || run.status === 'agent_running';
  const baseFeeZeroEnabled = quotationResults?.items.length
    ? quotationResults.items.every((quotation) => quotation.base_fee_override === 0)
    : false;
  return (
    <section className="mx-auto max-w-screen-2xl space-y-8 pt-10">
      {error ? <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <AgentRunStat label="运行 ID" value={run.run_id} />
          <AgentRunStat label="整体状态" value={formatAgentRunStatus(run.status)} status />
          <AgentRunStat label="最近更新" value={formatTimestamp(run.updated_at)} />
          <AgentRunStat label="原始文件" value={run.uploaded_file} />
        </div>
        <div className="glass-panel p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase text-slate-400">运行操作</p>
              <p className="text-sm font-medium text-slate-700">
                {run.status === 'submitted'
                  ? quotationResultsLoading
                    ? '报价已完成，正在加载报价结果。'
                    : quotationResultsError
                      ? '报价已完成，但加载报价结果失败。'
                      : '报价已完成，可查看、修改和下载当前结果。'
                  : '报价正在执行，请等待运行完成。'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={onRefresh} disabled={refreshing}>
                {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
                刷新状态
              </button>
              {run.status === 'submitted' && (quotationResultsLoading || quotationResultsError) ? (
                <button
                  type="button"
                  className="btn-secondary inline-flex items-center gap-2 text-xs"
                  onClick={onReloadQuotationResults}
                  disabled={quotationResultsLoading}
                >
                  {quotationResultsLoading ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
                  {quotationResultsLoading ? '正在加载结果...' : '重新加载结果'}
                </button>
              ) : null}
            </div>
          </div>
          {quotationResultsError ? <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{quotationResultsError}</div> : null}
          {quotationResultsOpen && quotationResults ? (
            <div className="mt-4 grid gap-4 border-t border-slate-100 pt-4 lg:grid-cols-2">
              <AgentRunLinkGroup title="导出文件">
                <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={onDownloadSource} disabled={sourceDownloading}>
                  {sourceDownloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  {sourceDownloading ? '正在下载...' : '下载源文件'}
                </button>
                <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={onExportAll} disabled={exporting || !quotationResults.items.some((item) => item.total_price !== null)}>
                  {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  {exporting ? '正在导出...' : '全部导出'}
                </button>
                <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={onExportSingle} disabled={exporting || activeQuotation?.total_price === null || activeQuotation === undefined}>
                  <Download size={14} />
                  单个导出
                </button>
              </AgentRunLinkGroup>
              <AgentRunLinkGroup title="报价数量">
                <span className="inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">{quotationResults.items.length} 项</span>
              </AgentRunLinkGroup>
              <AgentRunLinkGroup title="报价调整">
                <div className="inline-flex items-center gap-2 text-xs font-medium text-slate-600">
                  <span>基本金归0</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={baseFeeZeroEnabled}
                    aria-label="基本金归0"
                    className={`relative h-5 w-9 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${baseFeeZeroEnabled ? 'bg-indigo-600' : 'bg-slate-300'}`}
                    onClick={() => onSetBaseFeeZero(!baseFeeZeroEnabled)}
                    disabled={baseFeeUpdating || requoting || quotationResults.items.length === 0}
                  >
                    <span className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${baseFeeZeroEnabled ? 'translate-x-4' : ''}`} />
                  </button>
                  {baseFeeUpdating ? <Loader2 size={14} className="animate-spin text-indigo-500" /> : null}
                </div>
              </AgentRunLinkGroup>
              <AgentRunLinkGroup title="历史报价库">
                <button type="button" className="btn-secondary inline-flex items-center gap-2 text-xs" onClick={onSaveToHistory} disabled={historySaving || quotationResults.items.length === 0}>
                  {historySaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {historySaving ? '正在保存...' : '保存至历史报价库'}
                </button>
                {historySaveMessage ? <span className="inline-flex items-center px-1 text-xs font-medium text-emerald-600">{historySaveMessage}</span> : null}
              </AgentRunLinkGroup>
            </div>
          ) : null}
        </div>
      </div>
      {quotationResultsOpen && quotationResults ? (
        <div className="space-y-4">
          <AgentQuoteSwitcher quotations={quotationResults.items} activeQuoteId={activeQuotationId} onSelect={onSelectQuotation} />
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
            <h2 className="text-2xl font-bold text-slate-800">结构化报价报表</h2>
            <p className="text-sm font-medium text-slate-400">STRUCTURED QUOTE REPORT</p>
          </div>
          {activeQuotation ? (
            <>
              <StructuredReportGrid quotationResult={activeQuotation} onUpdated={onQuotationUpdated} saving={requoting} />
              <div className="flex justify-end">
                <button type="button" className="btn-primary inline-flex items-center gap-2 text-xs" onClick={() => onRecalculateQuotation()} disabled={requoting}>
                  {requoting ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                  {requoting ? '正在筛选设备...' : '按当前字段筛选设备并报价'}
                </button>
              </div>
              <EquipmentTables
                quotationResult={activeQuotation}
                selecting={requoting}
                onSelectDevice={(deviceCode) => onRecalculateQuotation(deviceCode)}
              />
            </>
          ) : <div className="glass-panel px-5 py-8 text-center text-sm font-medium text-slate-400">该运行未生成可展示的报价表。</div>}
        </div>
      ) : null}
    </section>
  );
}

function AgentRunStat({label, value, status = false}: {label: string; value: string; status?: boolean}) {
  return (
    <div className="glass-panel flex min-w-0 items-center gap-4 p-4">
      <div className="min-w-0">
        <p className="mb-0.5 text-[10px] font-bold uppercase text-slate-400">{label}</p>
        {status ? <span className="status-badge border border-emerald-200 bg-emerald-100 text-emerald-700">{value}</span> : <p className="truncate text-sm font-semibold text-slate-700" title={value}>{value}</p>}
      </div>
    </div>
  );
}

function AgentRunLinkGroup({title, children}: {title: string; children: React.ReactNode}) {
  return (
    <div>
      <p className="mb-2 text-[10px] font-bold uppercase text-slate-400">{title}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function AgentQuoteSwitcher({
  quotations,
  activeQuoteId,
  onSelect,
}: {
  quotations: AgentQuotationItem[];
  activeQuoteId: string;
  onSelect: (quoteId: string) => void;
}) {
  return (
    <div className="glass-panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-800">报价切换</h2>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500">{quotations.length} 项</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {quotations.map((quotation, index) => {
          const active = quotation.quote_id === activeQuoteId;
          const rawTestType = quotation.fixed_fields.raw_test_type;
          const title = rawTestType == null || rawTestType === '' ? `报价 ${index + 1}` : String(rawTestType);
          return (
            <button
              key={quotation.quote_id}
              type="button"
              onClick={() => onSelect(quotation.quote_id)}
              className={`min-w-56 rounded-lg border px-3 py-2 text-left transition-colors ${active ? 'border-indigo-200 bg-indigo-50 text-indigo-800' : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200'}`}
            >
              <div className="truncate text-sm font-bold">{title}</div>
              <div className="mt-1 truncate text-xs opacity-75">{quotation.quote_id}</div>
              <div className="mt-1 text-xs opacity-75">总价 {formatAgentCurrency(quotation.total_price)}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function formatAgentCurrency(value: number | null): string {
  return value === null ? 'null' : `¥${value.toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

function formatAgentRunStatus(status: string) {
  const labels: Record<string, string> = {
    created: '等待执行',
    agent_running: '正在报价',
    submitted: '报价完成',
    submission_rejected: '提交未通过',
    agent_failed: '报价失败',
  };
  return labels[status] ?? status;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {hour12: false});
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
