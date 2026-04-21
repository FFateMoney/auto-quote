# Auto Quote

Auto Quote 是一套自动报价系统，采用**单仓库微服务架构**，核心流程分为两条：

1. **报价流程**：用户上传文件 → 抽取 → 匹配 → 筛选 → 报价
2. **标准库流程**：原始 PDF → OCR → 清洗 → 向量索引

## 整体架构

```
┌─────────────┐
│   前端(React)   │
│   :3000     │
└──────┬──────┘
       │
   ┌───▼───────────────────┐
   │   报价服务 (:8000)    │
   │  backend/quote         │
   └───┬───────────┬────────┘
       │           │
  ┌────▼────┐  ┌───▼──────────┐
  │OCR:8001 │  │索引:8003     │
  │backend/ │  │backend/      │
  │ocr      │  │indexing      │
  └────┬────┘  └───▲──────────┘
       │           │
  ┌────▼───────────┴────┐
  │ 清洗:8002           │
  │ backend/cleaning    │
  └─────────────────────┘
       │
   ┌───▼─────────────────┐
   │   Qdrant 向量库     │
   │   (localhost:6333)  │
   └─────────────────────┘
```

## 服务职责

| 服务 | 职责 | 端口 |
|------|------|------|
| `backend/ocr` | PDF/图片 → Markdown | 8001 |
| `backend/cleaning` | Markdown 规范化清洗 | 8002 |
| `backend/indexing` | 分块、向量化、Qdrant 存储 | 8003 |
| `backend/quote` | 报价流程编排 | 8000 |

## 核心特性

- **多格式文档支持**：Word、Excel、PDF、Image
- **智能试验类型匹配**：本地规范化 + LLM 语义理解
- **设备智能筛选**：初筛 + 补充标准后复筛
- **多轮标准补充**：按章节范围递进式扩展，避免信息冗余
- **向量化检索**：使用 Qwen3-Embedding，支持中英文混合标准

## 安装

前端：
```bash
cd frontend/web
npm install
```

后端：
```bash
pip install -r backend/requirements.txt
```

依赖：
- Python 3.10+
- Node.js 16+
- PostgreSQL（设备/试验类型目录）
- Qdrant（向量索引）

## 配置

复制 `backend/dev/config.example.yaml` 为 `backend/dev/config.yaml`，至少补齐：
- `services.ocr`
- `services.cleaning`
- `services.indexing`
- `services.quote_service`
- `qwen`（LLM API）
- `database`（PostgreSQL）

### 关键配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `ocr.origin_dir` | `OCR_ORIGIN_DIR` | `data/origin` | 原始 PDF 目录 |
| `ocr.output_dir` | `OCR_OUTPUT_DIR` | `data/ocr_markdown` | OCR 输出 |
| `cleaning.input_dir` | `CLEANING_INPUT_DIR` | `data/ocr_markdown` | 清洗输入 |
| `cleaning.output_dir` | `CLEANING_OUTPUT_DIR` | `data/cleaned_markdown` | 清洗输出 |
| `indexing.input_dir` | `INDEXING_INPUT_DIR` | `data/cleaned_markdown` | 索引输入 |
| `indexing.qdrant_url` | `QDRANT_URL` | `http://localhost:6333` | Qdrant 服务地址 |

## 快速开始

### 一键启动（推荐）

```bash
python backend/dev/start_backend.py
```

这会同时启动所有后端服务：
- OCR：`http://127.0.0.1:8001`
- 清洗：`http://127.0.0.1:8002`
- 索引：`http://127.0.0.1:8003`
- 报价：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:3000`

### 分别启动

```bash
# 终端 1：OCR
python -m uvicorn backend.ocr.http.app:app --host 127.0.0.1 --port 8001

# 终端 2：清洗
python -m uvicorn backend.cleaning.http.app:app --host 127.0.0.1 --port 8002

# 终端 3：索引
python -m uvicorn backend.indexing.http.app:app --host 127.0.0.1 --port 8003

# 终端 4：报价
python -m uvicorn backend.quote.http.app:app --host 127.0.0.1 --port 8000

# 终端 5：前端
cd frontend/web && npm run dev
```

## 标准库管理

原始 PDF 放在 `data/origin/`，通过 OCR → 清洗 → 索引 三个阶段处理：

### 初始化标准库
```bash
# 1. OCR：PDF → Markdown
python -m backend.ocr sync

# 2. 清洗：规范化 Markdown
python -m backend.cleaning sync

# 3. 建库：向量化 + Qdrant
python -m backend.indexing sync
```

### 增量更新
放新的 PDF 到 `data/origin/`，重新运行上面的三个命令。系统会自动检测变化，只处理新增/修改的文件。

### 全量重建
```bash
python -m backend.ocr rebuild
python -m backend.cleaning rebuild
python -m backend.indexing rebuild
```

## 核心接口

### 报价 API

```bash
# 创建报价运行
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"file_name": "test.xlsx", "content": "..."}'

# 继续报价（人工补录后）
curl -X POST http://127.0.0.1:8000/api/runs/{run_id}/resume \
  -H "Content-Type: application/json" \
  -d '{"rows": [...]}'
```

### 其他服务接口

```bash
# 健康检查
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:8003/api/health

# 索引状态
curl http://127.0.0.1:8003/api/indexing/status
```

详细 API 文档见各服务的 `http/routes.py`。

## 仓库结构

```text
frontend/web/                   ← React 前端
backend/
  ├── common/                   ← 共享模型、工具
  ├── ocr/                      ← OCR 服务
  ├── cleaning/                 ← 清洗服务
  ├── indexing/                 ← 向量索引服务
  ├── quote/                    ← 报价服务
  └── dev/                      ← 开发启动脚本
data/
  ├── origin/                   ← 原始 PDF 文件（用户放入）
  ├── ocr_markdown/             ← OCR 输出的 Markdown
  ├── cleaned_markdown/         ← 清洗后的 Markdown
  └── standard_index/           ← Qdrant 向量索引
runtime/runs/                   ← 报价运行记录（可删除）
doc/                            ← 文档
```
