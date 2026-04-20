# Auto Quote Architecture Notes

当前仓库采用单仓库微服务结构：

- `frontend/web`：React 前端，只调用报价服务
- `backend/ocr`：OCR 服务，仅使用 PP-StructureV3，PDF/图片 → Markdown
- `backend/cleaning`：清洗服务，Markdown 文本规范化
- `backend/indexing`：向量索引服务，分块、向量化、Qdrant 存储
- `backend/quote`：报价编排、上传处理、标准检索、报价 API
- `backend/common`：共享模型、配置工具、日志

## 模块结构

### `backend/ocr/`
```
engine.py        # PpStructureV3Engine（懒加载 pipeline）
service.py       # OcrService（薄封装，process_bytes / process_path）
library.py       # LibraryBuilder（增量/全量扫描 data/origin/ → data/ocr_markdown/）
settings.py      # OcrSettings（读 services.ocr.* 或 OCR_* 环境变量）
models.py        # MarkdownResult
cli.py           # CLI：sync / rebuild / serve
http/app.py      # FastAPI 入口
http/routes.py   # /api/health、/api/ocr/markdown、/api/ocr/library/*
```

### `backend/cleaning/`
```
engine.py        # 清洗算法（BeautifulSoup + Regex）
service.py       # CleaningService（单文件清洗）
library.py       # CleaningLibrary（增量/全量扫描 data/ocr_markdown/ → data/claned_markdown/）
settings.py      # CleaningSettings（读 services.cleaning.* 或 CLEANING_* 环境变量）
models.py        # BatchReport
cli.py           # CLI：sync / rebuild
http/app.py      # FastAPI 入口
http/routes.py   # /api/clean、/api/cleaning/sync 等
```

### `backend/indexing/`
```
engine.py        # Qwen3EmbeddingEngine（向量化 + Rerank）
splitter.py      # MarkdownHeadingSplitter（按标题分块）
qdrant_store.py  # QdrantStore（Qdrant 客户端）
service.py       # IndexingService（向量化 + 入库）
library.py       # IndexingLibrary（增量/全量扫描 data/claned_markdown/ → Qdrant）
settings.py      # IndexingSettings（读 services.indexing.* 或 INDEXING_* 环境变量）
models.py        # StandardChunk、StandardMetadata、SearchResult
cli.py           # CLI：sync / rebuild
http/app.py      # FastAPI 入口
http/routes.py   # /api/indexing/sync 等
```

### `backend/quote/`
```
models.py          # 报价专属模型（FormRow、RunState 等）
settings.py        # QuoteSettings（读 services.quote_service.* 或 QUOTE_* 环境变量）
stages.py          # 阶段常量
form_ops.py        # merge_rows、apply_manual_values
run_store.py       # RunStore（JSON 序列化）
catalog.py         # CatalogGateway（PostgreSQL 设备/试验类型目录）
ocr_client.py      # OcrClient（HTTP 调用 backend/ocr 服务）
quoter.py          # Quoter（设备筛选、报价）
kernel.py          # Kernel（试验类型匹配、标准附件、标准证据解析）
standard_enrich.py # progressive_enrich（多轮 LLM 标准证据补表）
orchestrator.py    # QuoteOrchestrator（全流程编排）
adapters/word.py   # AIWord 脚本调用
adapters/excel.py  # Excel 预处理 + 图片 OCR
adapters/pdf.py    # PDF 按页渲染为图片
plugins/base.py    # DocumentProcessorPlugin 抽象基类
plugins/word.py    # Word 插件
plugins/excel.py   # Excel 插件
plugins/pdf.py     # PDF 插件（每页渲染为图 → 发给 LLM）
plugins/image.py   # 图片插件（OCR 出 Markdown + 原图 → 同时发给 LLM）
plugins/registry.py# PluginRegistry
standard/kb_reader.py  # StandardLibrary（查标准文件记录）
standard/retriever.py  # StandardRetriever（向量+关键词检索）
standard/resolver.py   # StandardResolver（章节范围解析）
standard/judge.py      # StandardContextJudge（LLM 判断证据相关性）
standard/module.py     # StandardRetrievalModule（组合检索+解析）
llm/requester.py       # QwenRequester（Qwen VL 模型客户端）
llm/prompts.json       # 提示词
http/app.py            # FastAPI 入口
http/routes.py         # /api/health、/api/runs、/api/runs/{id}/resume 等
```

## 运行边界

- 前端 (`3000`) → `backend/quote`（端口 8000）
- `backend/quote` → `backend/ocr`（端口 8001，HTTP）
- `backend/quote` → `backend/indexing`（端口 8003，HTTP 向量检索）
- `backend/cleaning` / `backend/indexing` 只读 `data/ocr_markdown/` / `data/claned_markdown/`
- 后端服务间完全隔离，仅通过 HTTP 通信

## 关键目录

```text
frontend/web/                 ← React 前端
backend/common/               ← 共享模型、工具
backend/ocr/                  ← OCR 服务
backend/cleaning/             ← 清洗服务
backend/indexing/             ← 向量索引服务
backend/quote/                ← 报价服务
backend/dev/                  ← 开发工具
data/
  ├── origin/                 ← 原始 PDF 文件
  ├── ocr_markdown/           ← OCR 输出的 Markdown
  ├── claned_markdown/        ← 清洗后的 Markdown
  └── standard_index/         ← Qdrant 向量索引
runtime/runs/                 ← 报价运行记录
doc/                          ← 文档
```

## 开发启动

```bash
python backend/dev/start_backend.py
```

这会同时启动所有服务：OCR (8001) + 清洗 (8002) + 索引 (8003) + 报价 (8000)

或分别启动：

```bash
python -m uvicorn backend.ocr.http.app:app --host 127.0.0.1 --port 8001
python -m uvicorn backend.cleaning.http.app:app --host 127.0.0.1 --port 8002
python -m uvicorn backend.indexing.http.app:app --host 127.0.0.1 --port 8003
python -m uvicorn backend.quote.http.app:app --host 127.0.0.1 --port 8000
cd frontend/web && npm run dev  # 端口 3000
```

## 标准库管理（OCR → 清洗 → 索引）

### OCR
```bash
python -m backend.ocr sync     # 增量同步 data/origin/ → data/ocr_markdown/
python -m backend.ocr rebuild  # 全量重建
```

### 清洗
```bash
python -m backend.cleaning sync     # 增量清洗 data/ocr_markdown/ → data/claned_markdown/
python -m backend.cleaning rebuild  # 全量重建
```

### 建库
```bash
python -m backend.indexing sync     # 增量索引 data/claned_markdown/ → Qdrant
python -m backend.indexing rebuild  # 全量重建
```

或通过 HTTP 调用对应端口的 `/api/*/sync` 和 `/api/*/rebuild` 接口。

## 实现约束

- 不允许在报价服务里直接初始化 OCR 引擎
- Paddle OCR 只允许使用官方工作流，不允许自己拼 prompt 调 `/v1` 聊天接口
- 图片上传：同时发送 OCR 生成的 Markdown 文本块 + 原始图片给 LLM（Direction B）
- `backend/ocr` 与 `backend/quote` 完全隔离，互不直接导入
- `backend/common` 只存放跨服务共享模型（DocumentAsset、NormalizedDocument、StandardDocumentRecord 等）
- 报价专属模型（FormRow、RunState 等）在 `backend/quote/models.py`
