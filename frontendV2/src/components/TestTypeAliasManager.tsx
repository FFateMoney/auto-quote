/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {Plus, RefreshCw, Save, Search, Trash2, X} from 'lucide-react';
import {fetchTestTypes, toErrorMessage, updateTestTypeAliases} from '../api';
import type {TestTypeOption} from '../types';

export const TestTypeAliasManager: React.FC = () => {
  const [items, setItems] = React.useState<TestTypeOption[]>([]);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [draftAliases, setDraftAliases] = React.useState<string[]>([]);
  const [newAlias, setNewAlias] = React.useState('');
  const [query, setQuery] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');

  const selected = React.useMemo(
    () => items.find((item) => item.id === selectedId),
    [items, selectedId],
  );
  const filteredItems = React.useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) {
      return items;
    }
    return items.filter((item) => {
      return item.name.toLowerCase().includes(text) || item.aliases.some((alias) => alias.toLowerCase().includes(text));
    });
  }, [items, query]);
  const dirty = selected ? normalizeAliasList(draftAliases).join('\n') !== normalizeAliasList(selected.aliases).join('\n') : false;

  React.useEffect(() => {
    void loadItems();
  }, []);

  React.useEffect(() => {
    if (!selected) {
      setDraftAliases([]);
      return;
    }
    setDraftAliases(selected.aliases);
    setNewAlias('');
    setNotice('');
    setError('');
  }, [selected?.id]);

  async function loadItems() {
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const data = await fetchTestTypes();
      setItems(data.items);
      setSelectedId((current) => {
        if (current != null && data.items.some((item) => item.id === current)) {
          return current;
        }
        return data.items[0]?.id ?? null;
      });
      if (data.load_error) {
        setError(`目录加载告警：${data.load_error}`);
      }
    } catch (loadError) {
      setError(toErrorMessage(loadError, '无法获取标准试验类型目录'));
    } finally {
      setLoading(false);
    }
  }

  function addAlias() {
    const alias = newAlias.trim();
    if (!alias) {
      return;
    }
    const next = normalizeAliasList([...draftAliases, alias]);
    setDraftAliases(next);
    setNewAlias('');
    setNotice('');
  }

  function removeAlias(alias: string) {
    setDraftAliases((current) => current.filter((item) => item !== alias));
    setNotice('');
  }

  async function saveAliases() {
    if (!selected || saving) {
      return;
    }
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const data = await updateTestTypeAliases(selected.id, normalizeAliasList(draftAliases));
      setItems((current) => current.map((item) => item.id === data.item.id ? data.item : item));
      setDraftAliases(data.item.aliases);
      setNotice(`${data.item.name} 已保存 ${data.item.aliases.length} 个同义词`);
      if (data.load_error) {
        setError(`目录刷新告警：${data.load_error}`);
      }
    } catch (saveError) {
      setError(toErrorMessage(saveError, '无法保存同义词'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-screen-2xl animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">标准试验类型同义词</h2>
          <p className="text-slate-400 text-sm font-medium">TEST TYPE ALIASES</p>
        </div>
        <button type="button" className="btn-secondary inline-flex items-center justify-center gap-2 text-xs" onClick={() => void loadItems()} disabled={loading || saving}>
          <RefreshCw size={14} className={loading ? 'animate-spin text-indigo-500' : 'text-indigo-500'} />
          刷新
        </button>
      </div>

      {error ? <div className="mb-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
      {notice ? <div className="mb-5 rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{notice}</div> : null}

      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="glass-panel overflow-hidden">
          <div className="border-b border-slate-100 p-4">
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
              <Search size={15} className="text-slate-400" />
              <input
                className="min-w-0 flex-1 bg-transparent text-sm font-medium text-slate-700 outline-none placeholder:text-slate-300"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索试验类型或同义词"
              />
              {query ? (
                <button type="button" className="text-slate-300 hover:text-slate-500" onClick={() => setQuery('')} aria-label="清空搜索">
                  <X size={14} />
                </button>
              ) : null}
            </div>
          </div>
          <div className="max-h-[68vh] overflow-y-auto p-2">
            {loading ? <div className="p-8 text-center text-sm text-slate-400">正在加载目录...</div> : null}
            {!loading && filteredItems.length === 0 ? <div className="p-8 text-center text-sm text-slate-400">没有匹配的标准试验类型。</div> : null}
            {!loading ? filteredItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`mb-2 w-full rounded-lg border px-3 py-3 text-left transition-colors ${item.id === selectedId ? 'border-indigo-200 bg-indigo-50 text-indigo-800' : 'border-transparent bg-white text-slate-700 hover:border-slate-200'}`}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="block text-sm font-bold">{item.name}</span>
                <span className="mt-1 block text-xs text-slate-400">计价单位：{item.pricing_mode || '-'} / 同义词：{item.aliases.length}</span>
              </button>
            )) : null}
          </div>
        </section>

        <section className="glass-panel min-w-0 p-5">
          {selected ? (
            <>
              <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <h3 className="truncate text-xl font-bold text-slate-800">{selected.name}</h3>
                  <p className="mt-1 text-xs font-mono text-slate-400">ID: {selected.id} / Pricing: {selected.pricing_mode || '-'}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-secondary inline-flex items-center gap-2 text-xs"
                    onClick={() => setDraftAliases(selected.aliases)}
                    disabled={!dirty || saving}
                  >
                    <X size={14} />
                    撤销
                  </button>
                  <button
                    type="button"
                    className="btn-primary inline-flex items-center gap-2 text-xs"
                    onClick={() => void saveAliases()}
                    disabled={!dirty || saving}
                  >
                    {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
                    保存
                  </button>
                </div>
              </div>

              <div className="mb-5 flex flex-col gap-2 sm:flex-row">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none focus:border-indigo-300"
                  value={newAlias}
                  onChange={(event) => setNewAlias(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      addAlias();
                    }
                  }}
                  placeholder="新增同义词"
                />
                <button type="button" className="btn-secondary inline-flex items-center justify-center gap-2 text-xs" onClick={addAlias}>
                  <Plus size={14} />
                  新增
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                {draftAliases.length > 0 ? draftAliases.map((alias) => (
                  <span key={alias} className="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700">
                    <span className="truncate">{alias}</span>
                    <button type="button" className="text-slate-300 hover:text-red-500" onClick={() => removeAlias(alias)} aria-label={`删除 ${alias}`}>
                      <Trash2 size={14} />
                    </button>
                  </span>
                )) : <div className="rounded-lg bg-slate-50 p-8 text-center text-sm text-slate-400">当前没有同义词。</div>}
              </div>
            </>
          ) : (
            <div className="rounded-lg bg-slate-50 p-12 text-center text-sm text-slate-400">请选择一个标准试验类型。</div>
          )}
        </section>
      </div>
    </div>
  );
};

function normalizeAliasList(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const alias = String(value || '').trim();
    const key = alias.toLowerCase();
    if (!alias || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(alias);
  }
  return result;
}
