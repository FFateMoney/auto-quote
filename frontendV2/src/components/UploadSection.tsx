/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {CheckCircle2, FilePlus2, FileText, Loader2, PackagePlus, Upload, X} from 'lucide-react';
import {motion} from 'motion/react';
import {fetchRunHistory, toErrorMessage} from '../api';
import type {RunHistoryItem} from '../types';

interface UploadSectionProps {
  error: string;
  isSubmitting: boolean;
  onStart: (files: File[]) => void;
  onLoadHistory: (runId: string) => void;
}

const ACCEPTED_FILES = '.doc,.docx,.xls,.xlsx,.pdf,.txt,.md,.csv,.png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff';
type InputMode = 'file' | 'text';

type SampleInformationDraft = {
  sampleCount: string;
  specificationM3: string;
  lengthMm: string;
  widthMm: string;
  heightMm: string;
};

const EMPTY_SAMPLE_INFORMATION: SampleInformationDraft = {
  sampleCount: '',
  specificationM3: '',
  lengthMm: '',
  widthMm: '',
  heightMm: '',
};

export const UploadSection: React.FC<UploadSectionProps> = ({error, isSubmitting, onStart, onLoadHistory}) => {
  const [inputMode, setInputMode] = React.useState<InputMode>('file');
  const [requirementFile, setRequirementFile] = React.useState<File | null>(null);
  const [referenceFiles, setReferenceFiles] = React.useState<File[]>([]);
  const [isDraggingReferences, setIsDraggingReferences] = React.useState(false);
  const [plainText, setPlainText] = React.useState('');
  const [sampleInformationOpen, setSampleInformationOpen] = React.useState(false);
  const [sampleInformation, setSampleInformation] = React.useState<SampleInformationDraft>(EMPTY_SAMPLE_INFORMATION);
  const [sampleInformationError, setSampleInformationError] = React.useState('');
  const [historyItems, setHistoryItems] = React.useState<RunHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [historyError, setHistoryError] = React.useState('');
  const trimmedText = plainText.trim();

  React.useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      setHistoryLoading(true);
      setHistoryError('');
      try {
        const data = await fetchRunHistory();
        if (!cancelled) {
          setHistoryItems(data.items);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setHistoryError(toErrorMessage(fetchError, '无法获取报价历史'));
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false);
        }
      }
    }
    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  function appendReferenceFiles(files: File[]) {
    setReferenceFiles((current) => [...current, ...files]);
  }

  function removeReferenceFile(index: number) {
    setReferenceFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
  }

  function handleReferenceDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDraggingReferences(false);
    appendReferenceFiles(Array.from(event.dataTransfer.files));
  }

  function openSampleInformationEditor() {
    setSampleInformation(EMPTY_SAMPLE_INFORMATION);
    setSampleInformationError('');
    setSampleInformationOpen(true);
  }

  function addSampleInformationFile() {
    const normalized = normalizeSampleInformation(sampleInformation);
    if (!normalized) {
      setSampleInformationError('请填写样品数量，并填写规格或完整的长、宽、高。');
      return;
    }
    appendReferenceFiles([
      new File([buildSampleInformationText(normalized)], '样品信息.txt', {type: 'text/plain;charset=utf-8'}),
    ]);
    setSampleInformationOpen(false);
  }

  function startQuotation() {
    const requirement = inputMode === 'file'
      ? requirementFile
      : new File([trimmedText], '报价需求.txt', {type: 'text/plain;charset=utf-8'});
    if (!requirement) {
      return;
    }
    onStart([requirement, ...referenceFiles]);
  }

  const hasRequirement = inputMode === 'file' ? requirementFile !== null : trimmedText.length > 0;

  return (
    <motion.div
      initial={{opacity: 0, y: 20}}
      animate={{opacity: 1, y: 0}}
      className="max-w-3xl mx-auto pt-16"
    >
      <div className="glass-panel p-8 text-center">
        <div className="mb-6">
          <div className="w-16 h-16 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-indigo-100">
            <Upload size={32} />
          </div>
          <h2 className="text-2xl font-bold text-slate-800">创建报价</h2>
          <p className="text-slate-500 mt-2">提供一个报价需求文档，并按需附加参考文件。</p>
        </div>

        <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 text-left">
          <div className="mb-2 flex items-center justify-between gap-3">
            <label htmlFor="run-history-select" className="text-sm font-bold text-slate-700">报价历史查询</label>
            {historyLoading ? (
              <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                <Loader2 size={12} className="animate-spin" />
                加载中
              </span>
            ) : null}
          </div>
          <select
            id="run-history-select"
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 outline-none transition-colors focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
            defaultValue=""
            disabled={historyLoading || isSubmitting || historyItems.length === 0}
            onChange={(event) => {
              const runId = event.target.value;
              if (!runId) {
                return;
              }
              onLoadHistory(runId);
              event.target.value = '';
            }}
          >
            <option value="">{historyItems.length > 0 ? '选择历史报价运行' : '暂无历史报价'}</option>
            {historyItems.map((item) => (
              <option key={item.run_id} value={item.run_id}>{item.label}</option>
            ))}
          </select>
          {historyError ? <div className="mt-2 text-xs font-medium text-red-600">{historyError}</div> : null}
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button
            type="button"
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${inputMode === 'file' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            onClick={() => setInputMode('file')}
          >
            上传需求文档
          </button>
          <button
            type="button"
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${inputMode === 'text' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            onClick={() => setInputMode('text')}
          >
            粘贴需求文本
          </button>
        </div>

        <section className="mb-5 text-left">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h3 className="text-sm font-bold text-slate-700">报价需求</h3>
            <span className="text-xs font-medium text-amber-700">报价需求文档只能有一个</span>
          </div>
          {inputMode === 'file' ? (
            <label className="relative block cursor-pointer">
              <input
                type="file"
                accept={ACCEPTED_FILES}
                onChange={(event) => setRequirementFile(event.target.files?.[0] ?? null)}
                className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
              />
              <div className={`rounded-xl border-2 border-dashed p-5 transition-colors ${requirementFile ? 'border-indigo-400 bg-indigo-50/30' : 'border-slate-200 bg-slate-50/50 hover:border-indigo-300'}`}>
                {requirementFile ? (
                  <FileItem file={requirementFile} onRemove={() => setRequirementFile(null)} />
                ) : (
                  <div className="flex items-center justify-center gap-2 text-sm text-slate-400">
                    <Upload size={18} />
                    <span>拖拽一个报价需求文档到此处，或点击选择</span>
                  </div>
                )}
              </div>
            </label>
          ) : (
            <div>
              <textarea
                value={plainText}
                onChange={(event) => setPlainText(event.target.value)}
                className="min-h-56 w-full resize-y rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-50"
                placeholder="在这里输入或粘贴测试项目、样品信息、标准号、试验条件等纯文本内容。"
              />
              <div className="mt-2 flex justify-end text-xs text-slate-400">{trimmedText.length}/100000</div>
            </div>
          )}
        </section>

        <section className="text-left">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-700">参考文件</h3>
              <p className="mt-0.5 text-xs text-slate-400">可选，可上传标准、客户附件、图片或其他补充资料。</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600" onClick={openSampleInformationEditor}>
                <PackagePlus size={15} />
                添加样品信息
              </button>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600">
                <FilePlus2 size={15} />
                添加文件
                <input
                  type="file"
                  accept={ACCEPTED_FILES}
                  multiple
                  className="sr-only"
                  onChange={(event) => {
                    appendReferenceFiles(Array.from(event.target.files ?? []));
                    event.target.value = '';
                  }}
                />
              </label>
            </div>
          </div>
          <div
            className={`rounded-xl border border-dashed transition-colors ${isDraggingReferences ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-slate-50'}`}
            onDragEnter={() => setIsDraggingReferences(true)}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDraggingReferences(true);
            }}
            onDragLeave={() => setIsDraggingReferences(false)}
            onDrop={handleReferenceDrop}
          >
            {referenceFiles.length > 0 ? (
              <div className="space-y-2 p-3">
              {referenceFiles.map((file, index) => (
                <div key={`${file.name}-${file.size}-${index}`}>
                  <FileItem file={file} onRemove={() => removeReferenceFile(index)} />
                </div>
              ))}
            </div>
            ) : (
              <div className="px-4 py-5 text-center text-xs text-slate-400">拖拽参考文件到此处，或点击添加文件</div>
            )}
          </div>
        </section>

        {error ? <div className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-left text-sm font-medium text-red-700">{error}</div> : null}

        <button
          type="button"
          onClick={startQuotation}
          disabled={!hasRequirement || trimmedText.length > 100_000 || isSubmitting}
          className="btn-primary mt-8 flex w-full items-center justify-center gap-2 disabled:opacity-50 disabled:shadow-none"
        >
          {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
          {isSubmitting ? '处理中...' : '开始智能报价'}
        </button>
      </div>
      {sampleInformationOpen ? (
        <SampleInformationDialog
          draft={sampleInformation}
          onChange={setSampleInformation}
          error={sampleInformationError}
          onClose={() => setSampleInformationOpen(false)}
          onSave={addSampleInformationFile}
        />
      ) : null}
    </motion.div>
  );
};

function SampleInformationDialog({
  draft,
  onChange,
  error,
  onClose,
  onSave,
}: {
  draft: SampleInformationDraft;
  onChange: (draft: SampleInformationDraft) => void;
  error: string;
  onClose: () => void;
  onSave: () => void;
}) {
  const calculatedSpecification = calculateSpecificationM3(draft);
  const specificationValue = calculatedSpecification ?? draft.specificationM3;

  function update(field: keyof SampleInformationDraft, value: string) {
    onChange({...draft, [field]: value});
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="presentation" onMouseDown={onClose}>
      <section className="w-full max-w-xl rounded-lg bg-white text-left shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="sample-information-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 id="sample-information-title" className="text-lg font-bold text-slate-800">添加样品信息</h3>
            <p className="mt-1 text-xs text-slate-400">填写规格，或填写完整长宽高自动计算规格立方米。</p>
          </div>
          <button type="button" className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700" onClick={onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <SampleInformationField label="样品数量">
            <input type="number" min="1" step="1" value={draft.sampleCount} onChange={(event) => update('sampleCount', event.target.value)} className={SAMPLE_INFORMATION_INPUT_CLASS} autoFocus />
          </SampleInformationField>
          <SampleInformationField label="规格 (m3)">
            <input type="number" min="0" step="any" value={specificationValue} onChange={(event) => update('specificationM3', event.target.value)} className={SAMPLE_INFORMATION_INPUT_CLASS} readOnly={calculatedSpecification !== null} />
          </SampleInformationField>
          <SampleInformationField label="长度 (mm)">
            <input type="number" min="0" step="any" value={draft.lengthMm} onChange={(event) => update('lengthMm', event.target.value)} className={SAMPLE_INFORMATION_INPUT_CLASS} />
          </SampleInformationField>
          <SampleInformationField label="宽度 (mm)">
            <input type="number" min="0" step="any" value={draft.widthMm} onChange={(event) => update('widthMm', event.target.value)} className={SAMPLE_INFORMATION_INPUT_CLASS} />
          </SampleInformationField>
          <SampleInformationField label="高度 (mm)">
            <input type="number" min="0" step="any" value={draft.heightMm} onChange={(event) => update('heightMm', event.target.value)} className={SAMPLE_INFORMATION_INPUT_CLASS} />
          </SampleInformationField>
        </div>
        {error ? <div className="mx-5 mb-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</div> : null}
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="btn-secondary text-sm" onClick={onClose}>取消</button>
          <button type="button" className="btn-primary text-sm" onClick={onSave}>添加到参考文件</button>
        </div>
      </section>
    </div>
  );
}

const SAMPLE_INFORMATION_INPUT_CLASS = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none transition-colors focus:border-indigo-300 focus:ring-4 focus:ring-indigo-50 read-only:cursor-not-allowed read-only:bg-slate-50';

function SampleInformationField({label, children}: {label: string; children: React.ReactNode}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-slate-700">{label}</span>
      {children}
    </label>
  );
}

function normalizeSampleInformation(draft: SampleInformationDraft): SampleInformationDraft | null {
  const sampleCount = positiveNumberText(draft.sampleCount);
  const dimensions = [draft.lengthMm, draft.widthMm, draft.heightMm].map(positiveNumberText);
  const hasDimensions = dimensions.some((value) => value !== null);
  if (!sampleCount || (hasDimensions && dimensions.some((value) => value === null))) {
    return null;
  }
  const calculatedSpecification = calculateSpecificationM3(draft);
  const specificationM3 = calculatedSpecification === null ? positiveNumberText(draft.specificationM3) : String(calculatedSpecification);
  if (!specificationM3) {
    return null;
  }
  return {
    sampleCount,
    specificationM3,
    lengthMm: dimensions[0] ?? '',
    widthMm: dimensions[1] ?? '',
    heightMm: dimensions[2] ?? '',
  };
}

function calculateSpecificationM3(draft: SampleInformationDraft): number | null {
  const dimensions = [draft.lengthMm, draft.widthMm, draft.heightMm].map(positiveNumberText);
  if (dimensions.some((value) => value === null)) {
    return null;
  }
  return Number(dimensions[0]) * Number(dimensions[1]) * Number(dimensions[2]) / 1_000_000_000;
}

function positiveNumberText(value: string): string | null {
  const numericValue = Number(value);
  return value.trim() && Number.isFinite(numericValue) && numericValue > 0 ? String(numericValue) : null;
}

function buildSampleInformationText(sampleInformation: SampleInformationDraft): string {
  const dimensions = [
    sampleInformation.lengthMm && `样品长度：${sampleInformation.lengthMm} mm`,
    sampleInformation.widthMm && `样品宽度：${sampleInformation.widthMm} mm`,
    sampleInformation.heightMm && `样品高度：${sampleInformation.heightMm} mm`,
  ].filter(Boolean);
  return [
    '样品信息',
    `样品数量：${sampleInformation.sampleCount} 件`,
    `样品规格：${sampleInformation.specificationM3} m3`,
    ...dimensions,
  ].join('\n');
}

function FileItem({file, onRemove}: {file: File; onRemove: () => void}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-white/80 px-3 py-2">
      <FileText className="shrink-0 text-indigo-600" size={18} />
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-700">{file.name}</span>
      <CheckCircle2 className="shrink-0 text-emerald-500" size={18} />
      <button
        type="button"
        className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
        onClick={onRemove}
        aria-label={`移除 ${file.name}`}
      >
        <X size={14} />
      </button>
    </div>
  );
}
