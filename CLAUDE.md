# Auto Quote 项目指南

## 项目概述

Auto Quote 是一个自动化报价系统，通过大模型和本地数据库匹配测试类型、筛选设备、计算价格。系统支持多种文档格式（Word、Excel、PDF、Image）的自动提取和处理。

## 核心架构

### 整体流程
```
上传文件 → 文档预处理 → 数据提取 → 类型匹配 → 设备初筛 → 标准补充 → 设备复筛 → 最终报价
```

### 分层设计

#### 1. **文档处理层** (`packages/plugins/` + `packages/integrations/`)
- **Plugins** (`packages/plugins/base.py`) - 文档处理器接口
  - `DocumentProcessorPlugin` - 抽象基类，所有文档处理器的父类
  - `can_handle(input_file)` - 判断是否能处理该文件类型
  - `preprocess(input_file)` - 执行预处理并返回标准化文档

- **现有插件**：
  - `WordProcessorPlugin` (.docx) - 调用AIWord导出内容
  - `ExcelProcessorPlugin` (.xlsx) - 调用ExcelAdapter提取表格
  - `PdfProcessorPlugin` (.pdf) - 调用PdfAdapter提取文本和图片
  - `ImageProcessorPlugin` (.png/.jpg) - 调用OcrAdapter进行OCR

- **Adapters** (`packages/integrations/`) - 格式适配器
  - `OcrAdapter` - 图片OCR识别（使用 rapidocr）
  - `ExcelAdapter` - Excel文件解析，提取表格和图片
  - `PdfAdapter` - PDF文本和图片提取
  - `AiwordAdapter` - 调用外部AIWord服务导出Word内容

#### 2. **业务逻辑层** (`packages/core/`)
- `orchestrator.py - QuoteOrchestrator` - 主编排器，协调整个流程
- `kernel.py - LocalKernel` - 本地内核
  - `attach_standard_refs()` - 关联标准文件
  - `match_test_types()` - 匹配试验类型
- `quoter.py - Quoter` - 报价器
  - `select_equipment()` - 筛选设备
  - `price()` - 计算价格
- `models.py` - 数据模型定义
- `stages.py` - 处理阶段定义
- `run_store.py` - 运行状态持久化

#### 3. **数据层** (`packages/integrations/`)
- `CatalogGateway` - 数据库连接，加载试验类型、设备、定价数据
- `StandardLibrary` - 标准文件库（本地文件系统）
- `StandardRetrievalModule` - 本地标准检索门面
  - `StandardRetriever` - 标准 chunk 检索
  - `StandardResolver` - 章节范围扩展（如 `5.1.3 -> 5.1.* -> 5.*`）
- `QwenRequester` - 大模型API调用（阿里云通义千问）

#### 4. **API层** (`apps/api/main.py`)
- FastAPI 应用
- `/api/runs` POST - 创建新的报价运行
- `/api/runs/{run_id}` GET - 获取运行状态
- `/api/runs/{run_id}/resume` POST - 恢复并继续报价
- `/api/runs/{run_id}/artifacts/{path}` GET - 下载产物文件

#### 5. **前端层** (`apps/web/`)
- React + TypeScript + Vite
- 文件上传、报价表编辑、结果查看

## 关键概念

### 1. NormalizedDocument（标准化文档）
所有文档处理器都返回这个格式，确保后续流程统一处理：
```python
class NormalizedDocument:
    document_id: str              # 文档ID
    source_name: str             # 原始文件名
    source_kind: str             # 来源类型（excel/word/pdf/image）
    text_blocks: list[NormalizedTextBlock]  # 文本块列表
    assets: list[DocumentAsset]  # 资产列表（主要是图片）
    metadata: dict               # 元数据
```

### 2. DocumentAsset（文档资产）
主要用于存储从文档中提取的图片：
```python
class DocumentAsset:
    asset_id: str                # 唯一ID (IMAGE_1, IMAGE_2...)
    mime_type: str              # MIME类型
    data_url: str               # Data URL (base64编码)
    position: str               # 位置信息（页码、行号等）
    context_text: str           # 上下文文本（用于大模型理解）
```

### 3. FormRow（表单行）
大模型提取出的数据结构，代表一个报价请求：
```python
class FormRow:
    row_id: str                 # 行ID
    raw_test_type: str          # 原始试验类型名称
    canonical_test_type: str    # 规范化后的试验类型
    pricing_quantity: float     # 计价数量
    repeat_count: float         # 重复次数/工件数，默认按 1 处理
    sample_length_mm, etc.      # 样品属性
    required_temp_min, etc.     # 需求条件
    source_refs: list[SourceRef] # 关联的标准文件
    standard_evidences: list[StandardEvidence] # 标准证据片段
    # ... 状态和结果字段
```

### 4. RunState（运行状态）
追踪整个报价流程的状态，包含所有中间结果和最终结果。

## 处理流程详解

### 阶段 1: DOCUMENT_EXTRACTED（文档抽取）
1. PluginRegistry 识别文件类型
2. 调用对应的 Plugin 进行预处理
3. 返回 NormalizedDocument
4. 调用 QwenRequester.extract_form() 使用大模型提取数据
5. 生成 FormRow 列表

### 阶段 2: TEST_TYPE_MATCHED（类型匹配）
1. LocalKernel.match_test_types() 将 raw_test_type 匹配到规范化的试验类型
2. 从 CatalogGateway 查询数据库中的试验类型记录
3. 填充 canonical_test_type 和 matched_test_type_id

### 阶段 3: EQUIPMENT_SELECTED（设备初筛）
1. Quoter.select_equipment() 根据试验类型找到候选设备
2. 检验样品属性和需求条件是否满足设备的约束条件
3. 生成 candidate_equipment_ids 和 rejected_equipment 列表
4. 得到可由标准补充的缺失字段，例如湿度、温变速率、位移等

### 阶段 4: STANDARD_ENRICHED（标准补充）
1. LocalKernel.attach_standard_refs() 根据标准号查找本地标准文件
2. LocalKernel.resolve_standard_evidences() 命中一个最高分三级标题，并按章节范围扩展：
   - 例如 `5.1.3 -> 5.1.* -> 5.*`
3. 范围扩展是增量发送：
   - `5.1.*` 不重复发送 `5.1.3`
   - `5.*` 只发送新进入范围的 `5.2 / 5.3 / ...`
4. 仅针对设备初筛后缺失、且可由标准补充的字段做逐轮补表
5. 一旦某个字段补出，就立即从剩余待补字段中移除；所有待补字段共享同一条扩展链和两次扩展次数

### 阶段 5: FINAL_QUOTED（最终报价）
1. 再次执行设备筛选，使用标准补充后的字段重新匹配设备
2. Quoter.price() 根据候选设备、计价数量和重复次数计算价格
3. 从 CatalogGateway 查询定价表
4. 当前计算公式：`总价 = (基础费 + 单价 × 计价数量) × 重复次数`
5. 如果无法完成报价，返回 `waiting_manual_input` 状态

## 文件结构导览

```
/my_storage/chen/auto-quote/
├── packages/
│   ├── core/                          # 核心业务逻辑
│   │   ├── orchestrator.py            # 主编排器
│   │   ├── kernel.py                  # 本地内核
│   │   ├── quoter.py                  # 报价器
│   │   ├── models.py                  # 数据模型
│   │   ├── stages.py                  # 处理阶段
│   │   ├── run_store.py               # 状态存储
│   │   └── form_ops.py                # 表单操作
│   ├── integrations/                  # 外部集成和适配器
│   │   ├── ocr_adapter.py             # OCR适配器
│   │   ├── pdf_adapter.py             # PDF适配器
│   │   ├── excel_adapter.py           # Excel适配器
│   │   ├── aiword_adapter.py          # Word导出适配器
│   │   ├── catalog.py                 # 数据库网关
│   │   ├── qwen_requester.py          # 大模型API
│   │   ├── standard_retrieval_module.py # 标准检索门面
│   │   ├── standard_retriever.py      # 标准 chunk 检索
│   │   ├── standard_resolution.py     # 章节范围扩展
│   │   ├── standard_indexer.py        # 本地标准索引构建
│   │   └── settings.py                # 配置管理
│   └── plugins/                       # 文档处理插件
│       ├── base.py                    # 插件接口
│       ├── excel_processor.py         # Excel插件
│       ├── pdf_processor.py           # PDF插件
│       ├── word_processor.py          # Word插件
│       ├── image_processor.py         # 图片插件
│       └── registry.py                # 插件注册表
├── apps/
│   ├── api/main.py                    # FastAPI应用
│   └── web/                           # React前端
├── standards/                         # 标准文件库（本地）
├── data/standard_index/               # 标准索引（持久化）
├── runtime/                           # 运行时数据（可删除）
├── config.yaml                        # 配置文件
└── requirements.txt                   # Python依赖
```

## 常见开发任务

### 添加新的文档格式支持
1. 在 `packages/integrations/` 创建 `{format}_adapter.py`
2. 在 `packages/plugins/` 创建 `{format}_processor.py`
3. 在 `packages/plugins/registry.py` 导入并注册新插件

示例：已完成的 PDF 支持
- `pdf_adapter.py` - 提取PDF文本和图片，OCR识别
- `pdf_processor.py` - 实现插件接口，调用适配器
- 在 `registry.py` 中注册

### 修改处理流程
编辑 `packages/core/orchestrator.py` 的 `run()` 和 `resume()` 方法。

### 修改大模型提示词
编辑 `prompts.json` 中的提示词，然后在 `packages/integrations/qwen_requester.py` 中调用。

### 修改数据库查询
编辑 `packages/integrations/catalog.py` 中的 SQL 查询和数据处理逻辑。

### 调试单个阶段
在 `packages/core/orchestrator.py` 中临时添加日志，查看 `runtime/runs/{run_id}/` 目录下的日志文件。

### 重建标准索引
```bash
python -m packages.integrations.standard_indexer --sync
python -m packages.integrations.standard_indexer --rebuild
```

## 重要配置

### config.yaml
```yaml
startup:
  backend_host: 127.0.0.1
  backend_port: 8000
  frontend_host: 127.0.0.1
  frontend_port: 5173
  auto_open_browser: true

database:
  host: localhost
  port: 5432
  dbname: auto_quote
  user: postgres
  password: ...

qwen:
  api_key: ...
  model: qwen3-omni-flash

integrations:
  standards_dir: ./standards
  standard_index_dir: ./data/standard_index
  prompts_path: ./prompts.json

runtime:
  run_dir: ./runtime/runs
```

## 依赖库

### 主要依赖
- **FastAPI** - Web框架
- **pypdf** - PDF处理
- **openpyxl** - Excel处理
- **Pillow** - 图片处理
- **rapidocr_onnxruntime** - OCR引擎
- **pydantic** - 数据验证
- **psycopg** - PostgreSQL驱动

## 运行和测试

```bash
# 安装依赖
pip install -r requirements.txt

# 启动（前后端）
python start.py

# 后端只
python -m uvicorn apps.api.main:app --reload

# 前端只
npm run web:dev
```

## 常见问题排查

### PDF处理失败
- 检查 `pypdf` 是否正确安装
- 查看 `runtime/runs/{run_id}/` 目录下的日志
- 某些加密或特殊格式的PDF可能无法处理

### 大模型API错误
- 检查 `config.yaml` 中的 API Key 和 Model 名称
- 查看 `QwenRequester` 的日志输出
- 调整提示词可能改善提取效果

### 数据库连接失败
- 检查 PostgreSQL 是否运行
- 验证 `config.yaml` 中的数据库连接信息
- 检查 `CatalogGateway.load_error` 字段

## 代码风格

- Python: PEP 8，使用 type hints
- 日志：使用 `logging` 模块，级别为 INFO/WARNING/ERROR
- 错误：使用 `RuntimeError` 抛出业务异常，错误消息格式 `error_type:detail:detail`
- 数据验证：使用 Pydantic BaseModel
- 路径处理：使用 `pathlib.Path`，避免字符串拼接

## 向Agent传递上下文的最佳实践

1. **描述要做什么** - 不要让Agent自己猜测
2. **指出相关文件** - 用 `packages/xxx/file.py` 格式指向具体位置
3. **提供示例** - 参考现有的Excel/Word处理来实现新功能
4. **说明数据流** - 明确输入输出的格式（NormalizedDocument等）
5. **指定修改范围** - 哪些文件需要改，哪些不要碰
