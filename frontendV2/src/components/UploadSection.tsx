/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {CheckCircle2, FileText, Loader2, Upload, X} from 'lucide-react';
import {motion} from 'motion/react';

interface UploadSectionProps {
  error: string;
  isSubmitting: boolean;
  onStart: (files: File[]) => void;
  onStartFromText: (text: string) => void;
}

const ACCEPTED_FILES = '.docx,.xlsx,.pdf,.png,.jpg,.jpeg,.bmp,.webp';
type InputMode = 'file' | 'text';

export const UploadSection: React.FC<UploadSectionProps> = ({error, isSubmitting, onStart, onStartFromText}) => {
  const [inputMode, setInputMode] = React.useState<InputMode>('file');
  const [selectedFiles, setSelectedFiles] = React.useState<File[]>([]);
  const [plainText, setPlainText] = React.useState('');
  const trimmedText = plainText.trim();

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(event.target.files ?? []));
  };

  const removeFile = (fileName: string) => {
    setSelectedFiles((current) => current.filter((file) => file.name !== fileName));
  };

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
          <h2 className="text-2xl font-bold text-slate-800">上传原始文档</h2>
          <p className="text-slate-500 mt-2">支持上传文档或直接粘贴纯文本需求。</p>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button
            type="button"
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${inputMode === 'file' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            onClick={() => setInputMode('file')}
          >
            上传文件
          </button>
          <button
            type="button"
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${inputMode === 'text' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
            onClick={() => setInputMode('text')}
          >
            粘贴文本
          </button>
        </div>

        {inputMode === 'file' ? (
          <div className="relative group cursor-pointer">
            <input
              type="file"
              accept={ACCEPTED_FILES}
              multiple
              onChange={handleFileChange}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
            />
            <div className={`border-2 border-dashed rounded-xl p-8 transition-colors ${selectedFiles.length > 0 ? 'border-indigo-400 bg-indigo-50/30' : 'border-slate-200 group-hover:border-indigo-300 bg-slate-50/50'}`}>
              {selectedFiles.length > 0 ? (
                <div className="space-y-3 text-left">
                  {selectedFiles.map((file) => (
                    <div key={`${file.name}-${file.size}`} className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-white/80 px-3 py-2">
                      <FileText className="text-indigo-600 shrink-0" size={18} />
                      <span className="min-w-0 flex-1 truncate font-medium text-slate-700">{file.name}</span>
                      <CheckCircle2 className="text-emerald-500 shrink-0" size={18} />
                      <button
                        type="button"
                        className="relative z-20 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        onClick={(event) => {
                          event.stopPropagation();
                          removeFile(file.name);
                        }}
                        aria-label={`移除 ${file.name}`}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-slate-400">
                  拖拽文件到此处 或 <span className="text-indigo-600 font-medium">点击选择</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-left">
            <textarea
              value={plainText}
              onChange={(event) => setPlainText(event.target.value)}
              className="min-h-56 w-full resize-y rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-50"
              placeholder="在这里输入或粘贴测试项目、样品信息、标准号、试验条件等纯文本内容。"
            />
            <div className="mt-2 flex justify-end text-xs text-slate-400">{trimmedText.length}/100000</div>
          </div>
        )}

        {error ? <div className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-left text-sm font-medium text-red-700">{error}</div> : null}

        <button
          type="button"
          onClick={() => inputMode === 'file' ? onStart(selectedFiles) : onStartFromText(trimmedText)}
          disabled={(inputMode === 'file' ? selectedFiles.length === 0 : trimmedText.length === 0 || trimmedText.length > 100_000) || isSubmitting}
          className="btn-primary w-full mt-8 disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-2"
        >
          {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
          {isSubmitting ? '处理中...' : '开始智能报价'}
        </button>
      </div>
    </motion.div>
  );
};
