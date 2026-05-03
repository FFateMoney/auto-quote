/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Activity, Clock, Download, FileCheck, Fingerprint, RefreshCw} from 'lucide-react';
import type {RunState, UploadedDocument} from '../types';

export const StatusDashboard: React.FC<{
  runState: RunState;
  onDocumentOpen: (event: React.MouseEvent<HTMLAnchorElement>, document: UploadedDocument) => void;
  onRefresh: () => void;
  artifactUrl: (artifactPath: string) => string;
  isRefreshing: boolean;
}> = ({runState, onDocumentOpen, onRefresh, artifactUrl, isRefreshing}) => {
  const uploadedFiles = runState.uploaded_documents.map((item) => item.file_name).join('、') || '-';
  const items = [
    {label: '运行 ID', value: runState.run_id, icon: Fingerprint},
    {label: '整体状态', value: runState.overall_status, icon: Activity, isStatus: true},
    {label: '当前阶段', value: runState.current_stage || '-', icon: Clock},
    {label: '原始文件', value: uploadedFiles, icon: FileCheck},
  ];

  return (
    <div className="space-y-4 mb-8">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {items.map((item) => (
          <div key={item.label} className="glass-panel p-4 flex items-center gap-4 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-slate-400 transition-colors shrink-0">
              <item.icon size={20} />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] uppercase font-bold text-slate-400 mb-0.5">{item.label}</p>
              {item.isStatus ? (
                <span className={`status-badge border ${getStatusColor(item.value)}`}>
                  {item.value.replace(/_/g, ' ')}
                </span>
              ) : (
                <p className="text-sm font-semibold text-slate-700 truncate" title={item.value}>{item.value}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="glass-panel p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-[10px] uppercase font-bold text-slate-400 mb-2">下一步</p>
            <p className="text-sm font-medium text-slate-700">{runState.next_action || '等待下一步'}</p>
          </div>
          <button type="button" className="btn-secondary text-xs flex items-center gap-2 self-start" onClick={onRefresh} disabled={isRefreshing}>
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin text-indigo-500' : 'text-indigo-500'} />
            刷新状态
          </button>
        </div>

        {runState.errors.length > 0 ? (
          <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {runState.errors.join('；')}
          </div>
        ) : null}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <LinkGroup title="上传文件">
            {runState.uploaded_documents.length > 0 ? runState.uploaded_documents.map((document) => (
              <a
                key={document.document_id}
                href={artifactUrl(document.stored_path)}
                onClick={(event) => onDocumentOpen(event, document)}
                className="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
              >
                <FileCheck size={14} className="shrink-0" />
                <span className="truncate">{document.file_name}</span>
              </a>
            )) : <EmptyText>暂无上传文件</EmptyText>}
          </LinkGroup>
          <LinkGroup title="导出文件">
            {runState.artifacts.exported_files.length > 0 ? runState.artifacts.exported_files.map((path) => (
              <a
                key={path}
                href={artifactUrl(path)}
                download
                className="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
              >
                <Download size={14} className="shrink-0" />
                <span className="truncate">{path.split('/').at(-1) ?? path}</span>
              </a>
            )) : <EmptyText>暂无导出文件</EmptyText>}
          </LinkGroup>
        </div>
      </div>
    </div>
  );
};

function getStatusColor(status: string) {
  switch (status) {
    case 'completed':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    case 'waiting_manual_input':
      return 'bg-amber-100 text-amber-700 border-amber-200';
    case 'running':
      return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'failed':
      return 'bg-red-100 text-red-700 border-red-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200';
  }
}

function LinkGroup({title, children}: {title: string; children: React.ReactNode}) {
  return (
    <div>
      <p className="text-[10px] uppercase font-bold text-slate-400 mb-2">{title}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function EmptyText({children}: {children: React.ReactNode}) {
  return <span className="text-xs text-slate-400">{children}</span>;
}
