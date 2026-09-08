import React from 'react';
import {Database, Pencil, Plus, RefreshCw, RotateCcw, Save, Server, Trash2, X} from 'lucide-react';
import {
  createCatalogTestProject,
  createCatalogDevice,
  deleteCatalogDevice,
  deleteCatalogTestProject,
  fetchCatalogDevices,
  fetchCatalogTestProjects,
  fetchDeletedCatalogDevices,
  fetchDeletedCatalogTestProjects,
  restoreCatalogDevice,
  restoreCatalogTestProject,
  toErrorMessage,
  updateCatalogTestProject,
  updateCatalogTestProjectAliases,
  type CatalogDevice,
  type CatalogDeviceDraft,
  type CatalogTestProject,
  type CatalogTestProjectDraft,
  updateCatalogDevice,
} from '../api';
import {getQuotationFieldLabel} from '../quotationFieldLabels';

type DatabaseTab = 'test-projects' | 'devices' | 'recycle-bin';

type StandardTypeGroup = {
  standardType: string;
  projects: CatalogTestProject[];
};

type ProjectFormDraft = {
  standard_type: string;
  test_item: string;
  max_specification: string;
  pricing_mode: string;
  base_fee: string;
  unit_price: string;
  applicable_device_codes: string[];
};

type ProjectEditor = {
  mode: 'create-project' | 'create-standard-type' | 'edit-project';
  testProjectId: number | null;
  draft: ProjectFormDraft;
};

type DeviceFormDraft = {
  device_code: string;
  capabilities: Record<string, string>;
};

type DeviceEditor = {
  deviceId: number | null;
  draft: DeviceFormDraft;
};

type AliasEditor = {
  testProjectId: number;
  testItem: string;
  aliases: string[];
  newAlias: string;
};

const FORM_INPUT_CLASS = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none transition-colors focus:border-indigo-300 focus:ring-4 focus:ring-indigo-50';

export const DatabaseManager: React.FC = () => {
  const [activeTab, setActiveTab] = React.useState<DatabaseTab>('test-projects');
  const [testProjects, setTestProjects] = React.useState<CatalogTestProject[]>([]);
  const [deletedTestProjects, setDeletedTestProjects] = React.useState<CatalogTestProject[]>([]);
  const [devices, setDevices] = React.useState<CatalogDevice[]>([]);
  const [deletedDevices, setDeletedDevices] = React.useState<CatalogDevice[]>([]);
  const [capabilityFields, setCapabilityFields] = React.useState<string[]>([]);
  const [editor, setEditor] = React.useState<ProjectEditor | null>(null);
  const [deviceEditor, setDeviceEditor] = React.useState<DeviceEditor | null>(null);
  const [aliasEditor, setAliasEditor] = React.useState<AliasEditor | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [mutatingProjectId, setMutatingProjectId] = React.useState<number | null>(null);
  const [mutatingDeviceId, setMutatingDeviceId] = React.useState<number | null>(null);
  const [error, setError] = React.useState('');
  const [editorError, setEditorError] = React.useState('');

  const standardTypeGroups = React.useMemo<StandardTypeGroup[]>(() => {
    const groups = new Map<string, CatalogTestProject[]>();
    for (const project of testProjects) {
      const projects = groups.get(project.standard_type) ?? [];
      projects.push(project);
      groups.set(project.standard_type, projects);
    }
    return Array.from(groups, ([standardType, projects]) => ({standardType, projects}));
  }, [testProjects]);
  const deviceCodes = React.useMemo(() => devices.map((device) => device.device_code), [devices]);
  const standardTypeOptions = React.useMemo(
    () => standardTypeGroups.map((group) => group.standardType),
    [standardTypeGroups],
  );
  const pricingModeOptions = React.useMemo(
    () => Array.from(new Set(testProjects.map((project) => project.pricing_mode))),
    [testProjects],
  );

  React.useEffect(() => {
    void loadCatalog();
  }, []);

  async function loadCatalog() {
    setLoading(true);
    setError('');
    try {
      const [projectResponse, deletedProjectResponse, deviceResponse, deletedDeviceResponse] = await Promise.all([
        fetchCatalogTestProjects(),
        fetchDeletedCatalogTestProjects(),
        fetchCatalogDevices(),
        fetchDeletedCatalogDevices(),
      ]);
      setTestProjects(projectResponse.items);
      setDeletedTestProjects(deletedProjectResponse.items);
      setDevices(deviceResponse.items);
      setDeletedDevices(deletedDeviceResponse.items);
      setCapabilityFields(deviceResponse.capability_fields);
    } catch (loadError) {
      setError(toErrorMessage(loadError, '无法读取数据库目录'));
    } finally {
      setLoading(false);
    }
  }

  function openCreateProjectEditor(standardType: string) {
    setEditor({
      mode: 'create-project',
      testProjectId: null,
      draft: {
        standard_type: standardType,
        test_item: '',
        max_specification: 'none',
        pricing_mode: '批次',
        base_fee: '0',
        unit_price: '0',
        applicable_device_codes: [],
      },
    });
    setEditorError('');
  }

  function openCreateStandardTypeEditor() {
    setEditor({
      mode: 'create-standard-type',
      testProjectId: null,
      draft: {
        standard_type: '',
        test_item: '',
        max_specification: 'none',
        pricing_mode: '批次',
        base_fee: '0',
        unit_price: '0',
        applicable_device_codes: [],
      },
    });
    setEditorError('');
  }

  function openEditEditor(project: CatalogTestProject) {
    setEditor({mode: 'edit-project', testProjectId: project.id, draft: toProjectFormDraft(project)});
    setEditorError('');
  }

  function openCreateDeviceEditor() {
    setDeviceEditor({
      deviceId: null,
      draft: {device_code: '', capabilities: emptyDeviceCapabilities(capabilityFields)},
    });
    setEditorError('');
  }

  function openEditDeviceEditor(device: CatalogDevice) {
    setDeviceEditor({deviceId: device.id, draft: toDeviceFormDraft(device, capabilityFields)});
    setEditorError('');
  }

  function openAliasEditor(project: CatalogTestProject) {
    setAliasEditor({
      testProjectId: project.id,
      testItem: project.test_item,
      aliases: [...project.aliases],
      newAlias: '',
    });
    setEditorError('');
  }

  async function saveProject() {
    if (!editor || saving) {
      return;
    }
    const draft = toCatalogTestProjectDraft(editor.draft);
    if (!draft) {
      setEditorError('请完整填写标准类型、测试项目、最大规格、计价方式、基本金和单价。');
      return;
    }
    setSaving(true);
    setEditorError('');
    setError('');
    try {
      if (editor.testProjectId === null) {
        await createCatalogTestProject(draft);
      } else {
        await updateCatalogTestProject(editor.testProjectId, draft);
      }
      setEditor(null);
      await loadCatalog();
    } catch (saveError) {
      setEditorError(toErrorMessage(saveError, '无法保存测试项目'));
    } finally {
      setSaving(false);
    }
  }

  function addAlias() {
    if (!aliasEditor) {
      return;
    }
    const alias = aliasEditor.newAlias.trim();
    if (!alias) {
      return;
    }
    setAliasEditor({...aliasEditor, aliases: [...aliasEditor.aliases, alias], newAlias: ''});
  }

  function removeAlias(index: number) {
    if (!aliasEditor) {
      return;
    }
    setAliasEditor({...aliasEditor, aliases: aliasEditor.aliases.filter((_, aliasIndex) => aliasIndex !== index)});
  }

  async function saveAliases() {
    if (!aliasEditor || saving) {
      return;
    }
    setSaving(true);
    setEditorError('');
    setError('');
    try {
      await updateCatalogTestProjectAliases(aliasEditor.testProjectId, aliasEditor.aliases);
      setAliasEditor(null);
      await loadCatalog();
    } catch (saveError) {
      setEditorError(toErrorMessage(saveError, '无法保存测试项目别名'));
    } finally {
      setSaving(false);
    }
  }

  async function deleteProject(project: CatalogTestProject) {
    if (mutatingProjectId !== null || !window.confirm(`确认将“${project.test_item} / ${project.max_specification}”移入回收站？`)) {
      return;
    }
    setMutatingProjectId(project.id);
    setError('');
    try {
      await deleteCatalogTestProject(project.id);
      await loadCatalog();
    } catch (deleteError) {
      setError(toErrorMessage(deleteError, '无法删除测试项目'));
    } finally {
      setMutatingProjectId(null);
    }
  }

  async function saveDevice() {
    if (!deviceEditor || saving) {
      return;
    }
    const draft = toCatalogDeviceDraft(deviceEditor.draft, capabilityFields);
    if (!draft) {
      setEditorError('请填写设备编号，且数值能力字段只能填写数字。');
      return;
    }
    setSaving(true);
    setEditorError('');
    setError('');
    try {
      if (deviceEditor.deviceId === null) {
        await createCatalogDevice(draft);
      } else {
        await updateCatalogDevice(deviceEditor.deviceId, draft);
      }
      setDeviceEditor(null);
      await loadCatalog();
    } catch (saveError) {
      setEditorError(toErrorMessage(saveError, '无法保存设备'));
    } finally {
      setSaving(false);
    }
  }

  async function deleteDevice(device: CatalogDevice) {
    if (mutatingDeviceId !== null || !window.confirm(`确认将设备“${device.device_code}”移入回收站？`)) {
      return;
    }
    setMutatingDeviceId(device.id);
    setError('');
    try {
      await deleteCatalogDevice(device.id);
      await loadCatalog();
    } catch (deleteError) {
      setError(toErrorMessage(deleteError, '无法删除设备'));
    } finally {
      setMutatingDeviceId(null);
    }
  }

  async function restoreProject(project: CatalogTestProject) {
    if (mutatingProjectId !== null) {
      return;
    }
    setMutatingProjectId(project.id);
    setError('');
    try {
      await restoreCatalogTestProject(project.id);
      await loadCatalog();
    } catch (restoreError) {
      setError(toErrorMessage(restoreError, '无法恢复测试项目'));
    } finally {
      setMutatingProjectId(null);
    }
  }

  async function restoreDevice(device: CatalogDevice) {
    if (mutatingDeviceId !== null) {
      return;
    }
    setMutatingDeviceId(device.id);
    setError('');
    try {
      await restoreCatalogDevice(device.id);
      await loadCatalog();
    } catch (restoreError) {
      setError(toErrorMessage(restoreError, '无法恢复设备'));
    } finally {
      setMutatingDeviceId(null);
    }
  }

  return (
    <div className="mx-auto max-w-screen-2xl animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">数据库管理</h2>
          <p className="mt-1 text-sm font-medium text-slate-400">测试项目与设备能力目录</p>
        </div>
        <button
          type="button"
          className="btn-secondary inline-flex items-center justify-center gap-2 text-xs"
          onClick={() => void loadCatalog()}
          disabled={loading || saving || mutatingProjectId !== null || mutatingDeviceId !== null}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin text-indigo-500' : 'text-indigo-500'} />
          刷新数据
        </button>
      </div>

      <div className="mb-5 inline-flex flex-wrap rounded-lg border border-slate-200 bg-slate-50 p-1">
        <TabButton active={activeTab === 'test-projects'} icon={Database} label="测试项目表" onClick={() => setActiveTab('test-projects')} />
        <TabButton active={activeTab === 'devices'} icon={Server} label="设备能力表" onClick={() => setActiveTab('devices')} />
        <TabButton active={activeTab === 'recycle-bin'} icon={Trash2} label={`回收站${deletedTestProjects.length + deletedDevices.length ? ` (${deletedTestProjects.length + deletedDevices.length})` : ''}`} onClick={() => setActiveTab('recycle-bin')} />
      </div>

      {error ? <div className="mb-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">正在读取数据库...</div>
      ) : activeTab === 'test-projects' ? (
        <TestProjectTable
          groups={standardTypeGroups}
          onCreateStandardType={openCreateStandardTypeEditor}
          onCreateProject={openCreateProjectEditor}
          onEdit={openEditEditor}
          onEditAliases={openAliasEditor}
          onDelete={(project) => void deleteProject(project)}
          mutatingProjectId={mutatingProjectId}
        />
      ) : activeTab === 'devices' ? (
        <DeviceCapabilityTable
          devices={devices}
          capabilityFields={capabilityFields}
          onCreate={openCreateDeviceEditor}
          onEdit={openEditDeviceEditor}
          onDelete={(device) => void deleteDevice(device)}
          mutatingDeviceId={mutatingDeviceId}
        />
      ) : (
        <RecycleBin
          projects={deletedTestProjects}
          devices={deletedDevices}
          onRestoreProject={(project) => void restoreProject(project)}
          onRestoreDevice={(device) => void restoreDevice(device)}
          mutatingProjectId={mutatingProjectId}
          mutatingDeviceId={mutatingDeviceId}
        />
      )}

      {editor ? (
        <TestProjectEditor
          editor={editor}
          deviceCodes={deviceCodes}
          standardTypeOptions={standardTypeOptions}
          pricingModeOptions={pricingModeOptions}
          saving={saving}
          error={editorError}
          onChange={setEditor}
          onClose={() => !saving && setEditor(null)}
          onSave={() => void saveProject()}
        />
      ) : null}
      {deviceEditor ? (
        <DeviceEditorDialog
          editor={deviceEditor}
          capabilityFields={capabilityFields}
          saving={saving}
          error={editorError}
          onChange={setDeviceEditor}
          onClose={() => !saving && setDeviceEditor(null)}
          onSave={() => void saveDevice()}
        />
      ) : null}
      {aliasEditor ? (
        <AliasEditorDialog
          editor={aliasEditor}
          saving={saving}
          error={editorError}
          onChange={setAliasEditor}
          onAdd={addAlias}
          onRemove={removeAlias}
          onClose={() => !saving && setAliasEditor(null)}
          onSave={() => void saveAliases()}
        />
      ) : null}
    </div>
  );
};

function TabButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ComponentType<{size?: number}>;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold transition-colors ${active ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
      onClick={onClick}
    >
      <Icon size={16} />
      {label}
    </button>
  );
}

function TestProjectTable({
  groups,
  onCreateStandardType,
  onCreateProject,
  onEdit,
  onEditAliases,
  onDelete,
  mutatingProjectId,
}: {
  groups: StandardTypeGroup[];
  onCreateStandardType: () => void;
  onCreateProject: (standardType: string) => void;
  onEdit: (project: CatalogTestProject) => void;
  onEditAliases: (project: CatalogTestProject) => void;
  onDelete: (project: CatalogTestProject) => void;
  mutatingProjectId: number | null;
}) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-sm font-bold text-slate-700">测试项目表</span>
        <button type="button" className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800" onClick={onCreateStandardType}>
          <Plus size={14} />
          添加标准类型
        </button>
      </div>
      {groups.length === 0 ? <EmptyTable message="测试项目表中暂无数据。" /> : <div className="overflow-x-auto border border-slate-200 bg-white">
        <table className="min-w-[980px] w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold text-slate-500">
          <tr>
            <th className="whitespace-nowrap px-4 py-3">标准类型</th>
            <th className="whitespace-nowrap px-4 py-3">测试项目</th>
            <th className="whitespace-nowrap px-4 py-3">最大规格</th>
            <th className="whitespace-nowrap px-4 py-3">计价方式</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">基本金</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">单价</th>
            <th className="whitespace-nowrap px-4 py-3">适配设备集合</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-700">
          {groups.map((group) => (
            <React.Fragment key={group.standardType}>
              <tr className="bg-slate-50/80">
                <td colSpan={8} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="text-sm font-bold text-slate-800">{group.standardType}</span>
                      <span className="ml-2 text-xs font-medium text-slate-400">{group.projects.length} 个测试项目</span>
                    </div>
                    <button type="button" className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800" onClick={() => onCreateProject(group.standardType)}>
                      <Plus size={14} />
                      添加测试项目
                    </button>
                  </div>
                </td>
              </tr>
              {group.projects.map((project) => (
                <tr key={project.id} className="hover:bg-indigo-50/30">
                  <td className="px-4 py-3 text-slate-300">└</td>
                  <td className="px-4 py-3 font-medium">
                    <button
                      type="button"
                      className="text-left text-indigo-700 hover:text-indigo-900 hover:underline"
                      title="管理测试项目别名"
                      onClick={() => onEditAliases(project)}
                    >
                      {project.test_item}
                      {project.aliases.length > 0 ? <span className="ml-1.5 text-xs font-medium text-slate-400">({project.aliases.length})</span> : null}
                    </button>
                  </td>
                  <td className="px-4 py-3">{project.max_specification}</td>
                  <td className="px-4 py-3">{project.pricing_mode}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatAmount(project.base_fee)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatAmount(project.unit_price)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">[{project.applicable_device_codes.join(', ')}]</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <IconButton icon={Pencil} label="编辑测试项目" onClick={() => onEdit(project)} disabled={mutatingProjectId !== null} />
                      <IconButton icon={Trash2} label="移入回收站" onClick={() => onDelete(project)} disabled={mutatingProjectId !== null} tone="danger" />
                    </div>
                  </td>
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>
        </table>
      </div>}
    </div>
  );
}

function RecycleBin({
  projects,
  devices,
  onRestoreProject,
  onRestoreDevice,
  mutatingProjectId,
  mutatingDeviceId,
}: {
  projects: CatalogTestProject[];
  devices: CatalogDevice[];
  onRestoreProject: (project: CatalogTestProject) => void;
  onRestoreDevice: (device: CatalogDevice) => void;
  mutatingProjectId: number | null;
  mutatingDeviceId: number | null;
}) {
  if (projects.length === 0 && devices.length === 0) {
    return <EmptyTable message="回收站为空。" />;
  }

  return (
    <div className="space-y-8">
      {projects.length > 0 ? <div>
        <h3 className="mb-3 text-sm font-bold text-slate-700">已删除测试项目</h3>
        <div className="overflow-x-auto border border-slate-200 bg-white">
          <table className="min-w-[900px] w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold text-slate-500">
          <tr>
            <th className="whitespace-nowrap px-4 py-3">标准类型</th>
            <th className="whitespace-nowrap px-4 py-3">测试项目</th>
            <th className="whitespace-nowrap px-4 py-3">最大规格</th>
            <th className="whitespace-nowrap px-4 py-3">计价方式</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">基本金</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">单价</th>
            <th className="whitespace-nowrap px-4 py-3">适配设备集合</th>
            <th className="whitespace-nowrap px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-700">
          {projects.map((project) => (
            <tr key={project.id} className="hover:bg-indigo-50/30">
              <td className="px-4 py-3">{project.standard_type}</td>
              <td className="px-4 py-3 font-medium">{project.test_item}</td>
              <td className="px-4 py-3">{project.max_specification}</td>
              <td className="px-4 py-3">{project.pricing_mode}</td>
              <td className="px-4 py-3 text-right tabular-nums">{formatAmount(project.base_fee)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{formatAmount(project.unit_price)}</td>
              <td className="px-4 py-3 font-mono text-xs text-slate-500">[{project.applicable_device_codes.join(', ')}]</td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onRestoreProject(project)}
                  disabled={mutatingProjectId !== null}
                >
                  <RotateCcw size={14} />
                  恢复
                </button>
              </td>
            </tr>
          ))}
        </tbody>
          </table>
        </div>
      </div> : null}
      {devices.length > 0 ? <DeletedDeviceTable devices={devices} onRestore={onRestoreDevice} mutatingDeviceId={mutatingDeviceId} /> : null}
    </div>
  );
}

function DeviceCapabilityTable({
  devices,
  capabilityFields,
  onCreate,
  onEdit,
  onDelete,
  mutatingDeviceId,
}: {
  devices: CatalogDevice[];
  capabilityFields: string[];
  onCreate: () => void;
  onEdit: (device: CatalogDevice) => void;
  onDelete: (device: CatalogDevice) => void;
  mutatingDeviceId: number | null;
}) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-sm font-bold text-slate-700">设备能力表</span>
        <button type="button" className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800" onClick={onCreate}>
          <Plus size={14} />
          添加设备
        </button>
      </div>
      {devices.length === 0 ? <EmptyTable message="设备能力表中暂无数据。" /> : <div className="overflow-x-auto border border-slate-200 bg-white">
      <table className="min-w-max w-full text-left text-xs">
        <thead className="border-b border-slate-200 bg-slate-50 font-bold text-slate-500">
          <tr>
            <th className="sticky left-0 z-10 whitespace-nowrap border-r border-slate-200 bg-slate-50 px-4 py-3">设备编号</th>
            {capabilityFields.map((field) => <th key={field} className="whitespace-nowrap px-4 py-3">{getQuotationFieldLabel(field)}</th>)}
            <th className="sticky right-0 z-10 whitespace-nowrap border-l border-slate-200 bg-slate-50 px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-700">
          {devices.map((device) => (
            <tr key={device.id} className="hover:bg-indigo-50/30">
              <td className="sticky left-0 z-10 whitespace-nowrap border-r border-slate-100 bg-white px-4 py-3 font-mono font-bold">{device.device_code}</td>
              {capabilityFields.map((field) => (
                <td key={field} className="whitespace-nowrap px-4 py-3 tabular-nums">{formatCapabilityValue(device.capabilities[field])}</td>
              ))}
              <td className="sticky right-0 z-10 border-l border-slate-100 bg-white px-4 py-3">
                <div className="flex justify-end gap-1">
                  <IconButton icon={Pencil} label="编辑设备" onClick={() => onEdit(device)} disabled={mutatingDeviceId !== null} />
                  <IconButton icon={Trash2} label="移入回收站" onClick={() => onDelete(device)} disabled={mutatingDeviceId !== null} tone="danger" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>}
    </div>
  );
}

function DeletedDeviceTable({
  devices,
  onRestore,
  mutatingDeviceId,
}: {
  devices: CatalogDevice[];
  onRestore: (device: CatalogDevice) => void;
  mutatingDeviceId: number | null;
}) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-bold text-slate-700">已删除设备</h3>
      <div className="overflow-x-auto border border-slate-200 bg-white">
        <table className="min-w-[420px] w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs font-bold text-slate-500">
            <tr>
              <th className="px-4 py-3">设备编号</th>
              <th className="px-4 py-3">非空能力数量</th>
              <th className="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {devices.map((device) => (
              <tr key={device.id} className="hover:bg-indigo-50/30">
                <td className="px-4 py-3 font-mono font-bold">{device.device_code}</td>
                <td className="px-4 py-3">{Object.values(device.capabilities).filter((value) => value !== null && value !== undefined && value !== '').length}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onRestore(device)} disabled={mutatingDeviceId !== null}>
                    <RotateCcw size={14} />
                    恢复
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TestProjectEditor({
  editor,
  deviceCodes,
  standardTypeOptions,
  pricingModeOptions,
  saving,
  error,
  onChange,
  onClose,
  onSave,
}: {
  editor: ProjectEditor;
  deviceCodes: string[];
  standardTypeOptions: string[];
  pricingModeOptions: string[];
  saving: boolean;
  error: string;
  onChange: (editor: ProjectEditor) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const {draft} = editor;
  const isNew = editor.testProjectId === null;
  const isNewStandardType = editor.mode === 'create-standard-type';

  function updateStandardType(value: string) {
    onChange({
      ...editor,
      draft: {
        ...draft,
        standard_type: value,
      },
    });
  }

  function updateDraft(field: keyof ProjectFormDraft, value: string | string[]) {
    onChange({
      ...editor,
      draft: {...draft, [field]: value},
    });
  }

  function toggleDevice(deviceCode: string) {
    const selected = new Set(draft.applicable_device_codes);
    if (selected.has(deviceCode)) {
      selected.delete(deviceCode);
    } else {
      selected.add(deviceCode);
    }
    updateDraft('applicable_device_codes', deviceCodes.filter((code) => selected.has(code)));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="presentation" onMouseDown={onClose}>
      <section className="max-h-[calc(100vh-2rem)] w-full max-w-3xl overflow-y-auto rounded-lg bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="test-project-editor-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 id="test-project-editor-title" className="text-lg font-bold text-slate-800">{isNewStandardType ? '新增标准类型' : isNew ? '新增测试项目' : '编辑测试项目'}</h3>
            <p className="mt-1 text-xs text-slate-400">适配设备仅可从设备能力表中选择。</p>
          </div>
          <IconButton icon={X} label="关闭" onClick={onClose} disabled={saving} />
        </div>

        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <FormField label="标准类型">
            {editor.mode === 'create-project' ? (
              <input value={draft.standard_type} readOnly className={`${FORM_INPUT_CLASS} cursor-not-allowed bg-slate-50 text-slate-500`} />
            ) : isNewStandardType ? (
              <input value={draft.standard_type} onChange={(event) => updateStandardType(event.target.value)} className={FORM_INPUT_CLASS} placeholder="例如：三综合" autoFocus />
            ) : (
              <select value={draft.standard_type} onChange={(event) => updateStandardType(event.target.value)} className={FORM_INPUT_CLASS}>
                {standardTypeOptions.map((standardType) => <option key={standardType} value={standardType}>{standardType}</option>)}
              </select>
            )}
          </FormField>
          <FormField label="测试项目">
            <input value={draft.test_item} onChange={(event) => updateDraft('test_item', event.target.value)} className={FORM_INPUT_CLASS} placeholder="例如：高低温循环" autoFocus={editor.mode === 'create-project'} />
          </FormField>
          <FormField label="最大规格">
            <input value={draft.max_specification} onChange={(event) => updateDraft('max_specification', event.target.value)} className={FORM_INPUT_CLASS} placeholder="例如：1（≤1m3）、2.4（2.4m3）、振动台或 none" />
          </FormField>
          <FormField label="计价方式">
            <select value={draft.pricing_mode} onChange={(event) => updateDraft('pricing_mode', event.target.value)} className={FORM_INPUT_CLASS}>
              {pricingModeOptions.map((pricingMode) => <option key={pricingMode} value={pricingMode}>{pricingMode}</option>)}
            </select>
          </FormField>
          <FormField label="基本金">
            <input type="number" min="0" step="0.01" value={draft.base_fee} onChange={(event) => updateDraft('base_fee', event.target.value)} className={FORM_INPUT_CLASS} />
          </FormField>
          <FormField label="单价">
            <input type="number" min="0" step="0.01" value={draft.unit_price} onChange={(event) => updateDraft('unit_price', event.target.value)} className={FORM_INPUT_CLASS} />
          </FormField>
          <div className="sm:col-span-2">
            <span className="mb-2 block text-sm font-semibold text-slate-700">适配设备集合</span>
            <div className="grid max-h-56 grid-cols-2 gap-2 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-3 md:grid-cols-4">
              {deviceCodes.map((deviceCode) => (
                <label key={deviceCode} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-slate-700 hover:bg-white">
                  <input type="checkbox" checked={draft.applicable_device_codes.includes(deviceCode)} onChange={() => toggleDevice(deviceCode)} className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
                  <span className="font-mono">{deviceCode}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {error ? <div className="mx-5 mb-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</div> : null}

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="btn-secondary text-sm" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-primary inline-flex items-center gap-2 text-sm" onClick={onSave} disabled={saving}>
            <Save size={15} />
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </section>
    </div>
  );
}

function DeviceEditorDialog({
  editor,
  capabilityFields,
  saving,
  error,
  onChange,
  onClose,
  onSave,
}: {
  editor: DeviceEditor;
  capabilityFields: string[];
  saving: boolean;
  error: string;
  onChange: (editor: DeviceEditor) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const {draft} = editor;
  const isNew = editor.deviceId === null;

  function updateCapability(field: string, value: string) {
    onChange({
      ...editor,
      draft: {
        ...draft,
        capabilities: {...draft.capabilities, [field]: value},
      },
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="presentation" onMouseDown={onClose}>
      <section className="max-h-[calc(100vh-2rem)] w-full max-w-6xl overflow-y-auto rounded-lg bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="device-editor-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 id="device-editor-title" className="text-lg font-bold text-slate-800">{isNew ? '新增设备' : '编辑设备'}</h3>
            <p className="mt-1 text-xs text-slate-400">空白能力字段将保存为 none。</p>
          </div>
          <IconButton icon={X} label="关闭" onClick={onClose} disabled={saving} />
        </div>

        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          <FormField label="设备编号">
            <input value={draft.device_code} onChange={(event) => onChange({...editor, draft: {...draft, device_code: event.target.value}})} className={FORM_INPUT_CLASS} />
          </FormField>
          {capabilityFields.map((field) => (
            <div key={field}>
            <FormField label={getQuotationFieldLabel(field)}>
              <input
                type={isTextCapability(field) ? 'text' : 'number'}
                step={isTextCapability(field) ? undefined : 'any'}
                value={draft.capabilities[field] ?? ''}
                onChange={(event) => updateCapability(field, event.target.value)}
                className={FORM_INPUT_CLASS}
              />
            </FormField>
            </div>
          ))}
        </div>

        {error ? <div className="mx-5 mb-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</div> : null}

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="btn-secondary text-sm" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-primary inline-flex items-center gap-2 text-sm" onClick={onSave} disabled={saving}>
            <Save size={15} />
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </section>
    </div>
  );
}

function AliasEditorDialog({
  editor,
  saving,
  error,
  onChange,
  onAdd,
  onRemove,
  onClose,
  onSave,
}: {
  editor: AliasEditor;
  saving: boolean;
  error: string;
  onChange: (editor: AliasEditor) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  function handleAliasInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      onAdd();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="presentation" onMouseDown={onClose}>
      <section className="w-full max-w-xl rounded-lg bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="alias-editor-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 id="alias-editor-title" className="text-lg font-bold text-slate-800">管理别名</h3>
            <p className="mt-1 text-sm font-medium text-slate-500">{editor.testItem}</p>
          </div>
          <IconButton icon={X} label="关闭" onClick={onClose} disabled={saving} />
        </div>

        <div className="space-y-4 p-5">
          <div className="flex gap-2">
            <input
              value={editor.newAlias}
              onChange={(event) => onChange({...editor, newAlias: event.target.value})}
              onKeyDown={handleAliasInputKeyDown}
              placeholder="输入别名"
              className={FORM_INPUT_CLASS}
              disabled={saving}
            />
            <button type="button" className="btn-secondary shrink-0 text-sm" onClick={onAdd} disabled={saving || !editor.newAlias.trim()}>
              添加
            </button>
          </div>

          {editor.aliases.length === 0 ? (
            <p className="py-5 text-center text-sm text-slate-400">尚未设置别名。</p>
          ) : (
            <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
              {editor.aliases.map((alias, index) => (
                <li key={`${alias}-${index}`} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                  <span className="min-w-0 break-words font-medium text-slate-700">{alias}</span>
                  <IconButton icon={Trash2} label={`删除别名 ${alias}`} onClick={() => onRemove(index)} disabled={saving} tone="danger" />
                </li>
              ))}
            </ul>
          )}
        </div>

        {error ? <div className="mx-5 mb-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</div> : null}

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="btn-secondary text-sm" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-primary inline-flex items-center gap-2 text-sm" onClick={onSave} disabled={saving}>
            <Save size={15} />
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </section>
    </div>
  );
}

function FormField({label, children}: {label: string; children: React.ReactNode}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-slate-700">{label}</span>
      {children}
    </label>
  );
}

function IconButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  tone = 'default',
}: {
  icon: React.ComponentType<{size?: number}>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: 'default' | 'danger';
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={`rounded-md p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tone === 'danger' ? 'text-slate-400 hover:bg-red-50 hover:text-red-600' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}
      onClick={onClick}
      disabled={disabled}
    >
      <Icon size={15} />
    </button>
  );
}

function EmptyTable({message}: {message: string}) {
  return <div className="border border-dashed border-slate-200 bg-slate-50 px-4 py-16 text-center text-sm text-slate-400">{message}</div>;
}

function toProjectFormDraft(project: CatalogTestProject): ProjectFormDraft {
  return {
    standard_type: project.standard_type,
    test_item: project.test_item,
    max_specification: project.max_specification,
    pricing_mode: project.pricing_mode,
    base_fee: String(project.base_fee),
    unit_price: String(project.unit_price),
    applicable_device_codes: project.applicable_device_codes,
  };
}

function toCatalogTestProjectDraft(draft: ProjectFormDraft): CatalogTestProjectDraft | null {
  const baseFee = Number(draft.base_fee);
  const unitPrice = Number(draft.unit_price);
  if (
    !draft.standard_type.trim()
    || !draft.test_item.trim()
    || !draft.max_specification.trim()
    || !draft.pricing_mode.trim()
    || !Number.isFinite(baseFee)
    || !Number.isFinite(unitPrice)
    || baseFee < 0
    || unitPrice < 0
  ) {
    return null;
  }
  return {
    standard_type: draft.standard_type.trim(),
    test_item: draft.test_item.trim(),
    max_specification: draft.max_specification.trim(),
    pricing_mode: draft.pricing_mode.trim(),
    base_fee: baseFee,
    unit_price: unitPrice,
    applicable_device_codes: draft.applicable_device_codes,
  };
}

function emptyDeviceCapabilities(capabilityFields: string[]): Record<string, string> {
  return Object.fromEntries(capabilityFields.map((field) => [field, '']));
}

function toDeviceFormDraft(device: CatalogDevice, capabilityFields: string[]): DeviceFormDraft {
  return {
    device_code: device.device_code,
    capabilities: Object.fromEntries(capabilityFields.map((field) => [field, device.capabilities[field] == null ? '' : String(device.capabilities[field])])),
  };
}

function toCatalogDeviceDraft(draft: DeviceFormDraft, capabilityFields: string[]): CatalogDeviceDraft | null {
  const capabilities: Record<string, unknown> = {};
  for (const field of capabilityFields) {
    const value = draft.capabilities[field]?.trim() ?? '';
    if (!value) {
      capabilities[field] = null;
      continue;
    }
    if (isTextCapability(field)) {
      capabilities[field] = value;
      continue;
    }
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return null;
    }
    capabilities[field] = numericValue;
  }
  if (!draft.device_code.trim()) {
    return null;
  }
  return {device_code: draft.device_code.trim(), capabilities};
}

function isTextCapability(field: string): boolean {
  return field === 'other_limits';
}

function formatAmount(value: number): string {
  return value.toLocaleString('zh-CN', {maximumFractionDigits: 2});
}

function formatCapabilityValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'none';
  }
  return String(value);
}
