# 系统设计说明文档

## 1. 文档目的

本文档描述 Auto Quote 系统的完整设计与实现，涵盖：

- **报价流程**：从用户上传文件到生成报价的完整路径
- **标准库流程**：从 PDF 到向量数据库的 OCR、清洗、建库全链路
- **核心数据模型**：系统中的关键对象与其生命周期
- **技术架构**：各服务的职责与交互方式
- **已实现与限制**：当前能力边界

如与历史讨论稿冲突，以当前代码实现为准。

## 2. 系统架构总览

Auto Quote 采用**微服务单仓库结构**：

```
┌─────────────────────────────────────────────────┐
│                    前端 (React)                   │
│              frontend/web:3000                   │
└────────────────┬────────────────────────────────┘
                 │ HTTP (同步长请求)
        ┌────────┴──────────────┐
        │                       │
   ┌────▼────────┐      ┌──────▼──────────┐
   │ 报价服务     │      │  标准库建库服务 │
   │ :8000       │      │  :8002/:8003    │
   │ quote       │      │  indexing/      │
   └────────────┘      │  cleaning       │
                       └──────────────────┘
        │                       │
   ┌────▼────────┐      ┌──────▼──────────┐
   │ OCR 服务     │      │ Qdrant 向量库   │
   │ :8001       │      │  (localhost)    │
   │ ocr         │      └──────────────────┘
   └────────────┘
```

### 核心服务职责

| 服务 | 职责 | 端口 |
|------|------|------|
| `backend/ocr` | PDF 转 Markdown，支持增量/全量 | 8001 |
| `backend/cleaning` | Markdown 文本清洗 | 8003 |
| `backend/indexing` | 建库、向量化、Qdrant 存储 | 8002 |
| `backend/quote` | 报价流程编排 | 8000 |

---

## 3. 报价流程（QuoteOrchestrator）

### 3.1 整体流程

用户上传文件 → 文档预处理 → 文档抽取 → 试验类型匹配 → 设备初筛 → 标准补充 → 设备复筛 → 最终报价

### 3.2 阶段定义

系统定义 5 个阶段（在 `backend/quote/stages.py`）：

| 阶段 | 输入 | 处理 | 输出 |
|------|------|------|------|
| `document_extracted` | 上传的 Word/Excel/PDF/Image | 使用插件提取表格/文本 | `FormRow` 列表 |
| `test_type_matched` | 原始试验类型文本 | Qwen LLM 匹配标准试验类型 | `canonical_test_type` + `standard_codes` |
| `equipment_selected` v1 | 试验条件、样品规格 | 从设备库筛选满足条件的设备 | `candidate_equipment_ids` |
| `standard_enriched` | 缺失字段 + 标准文本 | 多轮 LLM 从标准中提取缺失值 | 补充后的缺失字段 |
| `equipment_selected` v2 | 补充后的试验条件 | 再次筛选设备 | `selected_equipment_id` |
| `final_quoted` | 选中的设备 + 报价规则 | 计算报价 | `base_fee` + `unit_price` + `total_price` |

### 3.3 核心数据结构：FormRow

`FormRow` 是系统的唯一业务对象，定义在 `backend/quote/models.py`。

**识别类字段**：
- `row_id`：行标识
- `raw_test_type`：原始试验类型文本
- `canonical_test_type`：标准化后的试验类型
- `standard_codes`：关联的标准号列表（如 `['GB/T 2411', 'GB/T 2423']`）

**样品类字段**：
- `sample_length_mm`、`sample_width_mm`、`sample_height_mm`、`sample_weight_kg`

**试验条件类字段**：
- 温度：`required_temp_min`、`required_temp_max`
- 湿度：`required_humidity_min`、`required_humidity_max`
- 温变速率：`required_temp_change_rate`
- 频率：`required_freq_min`、`required_freq_max`
- 加速度、位移、辐照度、水温、水流量等

**报价相关字段**：
- `pricing_mode`：计价方式（如”小时数”、”件数”）
- `pricing_quantity`：单次计价量（如 5 小时）
- `repeat_count`：重复次数（如 3 件）
- 公式：`总价 = (基础费 + 单价 × 计价数量) × 重复次数`

**结果字段**：
- `candidate_equipment_ids`：初筛候选设备列表
- `selected_equipment_id`：最终选中设备
- `rejected_equipment`：被筛设备及原因
- `missing_fields`：未补齐的字段列表（中文标签）
- `blocking_reason`：阻塞原因
- `standard_evidences`：从标准中提取的文本证据
- `standard_match_notes`：标准匹配笔记

---

## 4. 标准库全流程（OCR → 清洗 → 建库）

### 4.1 目录结构

```
standards/origin/          ← 用户上传的原始 PDF（仅供 OCR）
data/
  ├── ocr_markdown/        ← OCR 输出的 Markdown
  ├── cleaned_markdown/    ← 清洗后的 Markdown
  └── standard_index/      ← 向量索引（Qdrant）
```

### 4.2 OCR 流程（backend/ocr）

**输入**：`standards/origin/` 目录下的 PDF 文件
**输出**：`data/ocr_markdown/` 下的 `.md` 文件

```
PDF 文件
  ↓
LibraryBuilder 扫描 origin_dir
  ↓
增量判断（计算文件 SHA-256，与缓存对比）
  ├─ 若 hash 未变：跳过
  └─ 若 hash 已变：触发 OCR
  ↓
OcrService.process_bytes()
  ↓
PP-StructureV3 模型（Paddle OCR）
  ↓
生成 Markdown（包含表格、图片说明等）
  ↓
输出至 data/ocr_markdown/{filename}.md
  ↓
更新同步状态
```

**关键特性**：
- **增量同步**：支持 `sync` 和 `rebuild` 两种模式
- **同步状态**：`sync_state/sync_state.json`，记录已处理文件的 SHA-256 与下游产物映射
- **容错机制**：单个文件失败不中断其他文件
- **报告**：返回 `LibraryBuildReport`（成功数、失败数、耗时）

**调用方式**：
```bash
# CLI
python -m backend.ocr.cli sync           # 增量同步
python -m backend.ocr.cli rebuild        # 全量重建

# HTTP
POST http://127.0.0.1:8001/api/ocr/library/sync
POST http://127.0.0.1:8001/api/ocr/library/rebuild
```

### 4.3 清洗流程（backend/cleaning）

**输入**：`data/ocr_markdown/` 下的 Markdown 文件
**输出**：`data/cleaned_markdown/` 下的清洗后 Markdown 文件

```
OCR 生成的 Markdown
  ↓
CleaningLibrary 扫描 input_dir
  ↓
增量判断（计算文件 SHA-256）
  ├─ 若 hash 未变：跳过
  └─ 若 hash 已变：触发清洗
  ↓
CleaningService.clean_markdown()
  ↓
执行清洗规则：
  ├─ 移除 HTML 标签
  ├─ 规范化空白符
  ├─ 修复编码问题
  ├─ 提取表格结构
  └─ 保留关键语义标记
  ↓
输出至 data/cleaned_markdown/{filename}.md
  ↓
更新同步状态
```

**关键特性**：
- **增量清洗**：同样支持 `sync` 和 `rebuild`
- **同步状态**：`sync_state/sync_state.json`
- **错误隔离**：单文件失败不阻塞其他文件
- **报告**：返回 `BatchReport`

### 4.4 建库流程（backend/indexing）

**输入**：`data/cleaned_markdown/` 下的清洗后 Markdown 文件
**输出**：Qdrant 向量数据库中的向量化索引

```
清洗后的 Markdown
  ↓
IndexingLibrary 扫描 input_dir（即 cleaned_markdown/）
  ↓
增量判断
  ├─ 若 hash 未变：跳过
  └─ 若 hash 已变：重新索引
  ↓
MarkdownHeadingSplitter 进行分块：
  ├─ 按 Markdown 标题层级结构分块（# ## ### 等）
  ├─ 若单块超过 max_chunk_bytes (500KB)：递归按段落、行继续分割
  └─ 保留 sequence_id 追踪同一标题下的分块序号
  ↓
IndexingService.index_file()
  ├─ 删除该文件的旧索引
  ├─ 批量向量化（batch_size=32）：
  │   ├─ 调用 Qwen3EmbeddingEngine.embed_texts()
  │   ├─ 每批后清理 GPU 显存（torch.cuda.empty_cache）
  │   └─ 防止 VRAM 溢出
  ├─ 批量写入 Qdrant（自适应降级策略）：
  │   ├─ 尝试批大小 256
  │   ├─ 若 Payload 超过 32MB 限制，降级到 64、32、16、8
  │   └─ 保证最终入库成功
  └─ 返回入库的总 chunk 数
  ↓
更新 hash 缓存（每文件成功后立即保存，支持断点续传）
  ↓
返回 IndexingReport（总文件数、已处理数、总 chunks 数、失败数）
```

**关键特性**：
- **按标题分块**：`MarkdownHeadingSplitter` 保持语义完整性，同时限制块大小
- **3 层分割策略**：
  1. 按标题层级分割
  2. 按段落（空行分隔）分割
  3. 按行分割（处理超大单段）
- **Sequence ID**：同一标题下的多块可通过 `sequence_id` 追踪
- **GPU 内存管理**：
  - 分批向量化（32 个 chunks/批）
  - 每批后清理缓存
  - 防止 OOM
- **Qdrant 自适应降级**：
  - 自动检测 Payload 大小限制（32MB）
  - 动态调整批大小：256 → 64 → 32 → 16 → 8
  - 保证 100% 入库成功率
- **增量建库**：
  - hash 缓存支持断点续传
  - 删除的文件自动清理
  - 修改的文件自动重建

**调用方式**：
```bash
# CLI
python -m backend.indexing sync        # 增量建库
python -m backend.indexing rebuild     # 全量重建

# HTTP
POST http://127.0.0.1:8002/api/indexing/sync
POST http://127.0.0.1:8002/api/indexing/rebuild
```

### 4.5 向量检索（在报价流程中）

当 FormRow 的 `standard_codes` 确定后，进行标准检索：

```
FormRow.standard_codes = ['GB/T 2411', 'GB/T 2423']
  ↓
StandardRetriever.retrieve_by_codes()
  ├─ 规范化 code：'GB/T 2411' → 'gbt2411'
  ├─ 在 Qdrant 中按 metadata 过滤
  └─ 返回匹配的 chunks
  ↓
StandardResolver.resolve_evidences()
  ├─ 找到最高分三级标题（如 5.1.3）
  ├─ 生成范围扩展链：5.1.3 → 5.1.* → 5.*
  └─ 支持多轮增量发送
  ↓
StandardContextJudge（LLM 判断相关性）
  ├─ 输入：缺失字段 + 标准文本
  └─ 输出：是否相关 + 抽取的值
```

---

## 5. 当前技术基线

| 组件 | 选择 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | 异步高性能 |
| 前端框架 | React + TypeScript | 类型安全 |
| OCR 模型 | PP-StructureV3 | Paddle 官方，支持表格识别 |
| 向量模型 | Qwen3-Embedding | 阿里通义模型 |
| LLM | Qwen3-Omni-Flash | 多模态理解 |
| 向量库 | Qdrant | 单机部署，32MB Payload 限制 |
| 数据持久化 | JSON + Qdrant | 运行状态 + 向量索引 |

---

## 6. 数据流向总结

```
用户上传文件
  ↓
backend/quote 调用 backend/ocr 获取 Markdown
  ↓
backend/quote 从 backend/indexing 查询标准
  ↓
backend/quote 组织报价表
  ↓
前端展示结果
```

**注意**：`backend/ocr` 和 `backend/quote` 完全隔离，不存在导入关系。中间通过 HTTP 接口通信。

---

## 7. 当前已实现的关键能力

### 7.1 OCR 层面

- ✅ PDF 提取 Markdown（表格、标题层级）
- ✅ 增量同步 + 全量重建
- ✅ 哈希缓存 + 容错

### 7.2 清洗层面

- ✅ OCR 结果清洗规范化
- ✅ 增量同步 + 全量重建
- ✅ 文本结构保留

### 7.3 建库层面

- ✅ 标题驱动的语义分块（sequence_id）
- ✅ 自适应大小分割（段落 → 行）
- ✅ 向量化 + Qdrant 存储
- ✅ GPU 内存优化（分批、清理）
- ✅ Qdrant Payload 自适应降级（256→64→32→16→8）
- ✅ 增量建库 + 断点续传
- ✅ 删除文件自动清理

### 7.4 报价层面

- ✅ 多格式文档支持（Word/Excel/PDF/Image）
- ✅ 试验类型标准化匹配
- ✅ 设备初筛 + 复筛
- ✅ 多轮标准补充（增量范围扩展）
- ✅ 报价公式支持重复次数
- ✅ 人工补录 + 继续报价

---

## 8. 当前系统限制

### 8.1 报价流程

- 后端仍采用同步长请求模型（无异步任务）
- 前端不轮询，只支持一次完整请求
- 标准补充仍依赖本地库（无网络标准源）

### 8.2 向量索引

- Qdrant 单机部署（无分布式）
- 32MB Payload 限制（通过自适应降级突破）
- 向量维度固定为 3072（Qwen3-Embedding）

### 8.3 文档处理

- PDF 按页转图（保留原始像素）
- Excel 无表头时首行不被丢弃（但需明确指示）
- 图片直接送 LLM（不再 OCR）

---

## 9. 后续优先级

### P0：稳定性

- 标准补充端到端回归样例
- 典型标准字段覆盖测试
- 标准补充日志增强

### P1：增强功能

- 温变速率推导规则
- 表格型标准页解析增强
- 扫描版 PDF 的 OCR 可靠性

### P2：架构演进

- 若 run 时间持续增长，改为异步任务 + 轮询
- 前端改为：创建 run → 返回 run_id → 轮询 status

---

## 10. 启动与运维

## 10. 启动与运维

### 10.1 开发启动

```bash
# 一键启动所有服务（前端 + 4 个后端服务）
python backend/dev/start_backend.py

# 或分别启动
python -m uvicorn backend.ocr.http.app:app --host 127.0.0.1 --port 8001
python -m uvicorn backend.indexing.http.app:app --host 127.0.0.1 --port 8002
python -m uvicorn backend.cleaning.http.app:app --host 127.0.0.1 --port 8003
python -m uvicorn backend.quote.http.app:app --host 127.0.0.1 --port 8000
cd frontend/web && npm run dev
```

### 10.2 标准库维护

**OCR 同步/重建**：
```bash
# 增量同步（检查 hash，只处理变化的文件）
python -m backend.ocr sync

# 全量重建（删除所有输出，从头开始）
python -m backend.ocr rebuild
```

**清洗同步/重建**：
```bash
python -m backend.cleaning sync
python -m backend.cleaning rebuild
```

**建库同步/重建**：
```bash
python -m backend.indexing sync
python -m backend.indexing rebuild
```

### 10.3 目录管理

运行时产生的目录可以安全删除：
- `runtime/runs/` — 存储用户的报价运行记录

重要的持久化数据（保留）：
- `data/ocr_markdown/*.md` — OCR 输出
- `data/cleaned_markdown/*.md` — 清洗后的数据
- `data/ocr_markdown/sync_state/` — OCR 同步状态
- `data/cleaned_markdown/sync_state/` — 清洗与建库同步状态
- `data/standard_index/` — Qdrant 向量库

---

## 11. FormRow 详细数据模型

`FormRow` 定义在 `backend/quote/models.py`，是系统的唯一业务对象。

### 11.1 字段分类与说明

**识别与关联**：
```python
row_id: str                          # 行 ID
raw_test_type: str                   # 原始试验类型文本
canonical_test_type: str             # 标准化后的试验类型名
standard_codes: list[str]            # 关联的标准号（如 ['GB/T 2411', 'GB/T 2423']）
```

**样品规格**：
```python
sample_length_mm: float | None       # 长（mm）
sample_width_mm: float | None        # 宽（mm）
sample_height_mm: float | None       # 高（mm）
sample_weight_kg: float | None       # 重量（kg）
```

**试验条件** — 温度类：
```python
required_temp_min: float | None      # 最低温度（°C）
required_temp_max: float | None      # 最高温度（°C）
required_temp_change_rate: float | None  # 温度变化速率（°C/min）
```

**试验条件** — 其他：
```python
required_humidity_min: float | None
required_humidity_max: float | None
required_freq_min: float | None
required_freq_max: float | None
required_accel_min: float | None
required_accel_max: float | None
required_displacement_min: float | None
required_displacement_max: float | None
required_irradiance_min: float | None
required_irradiance_max: float | None
required_water_temp_min: float | None
required_water_temp_max: float | None
required_water_flow_min: float | None
required_water_flow_max: float | None
```

**报价相关**：
```python
pricing_mode: str | None             # 计价方式（”小时数”、”件数”、”天数” 等）
pricing_quantity: float | None       # 单次计价量（如 5 小时）
repeat_count: int | None             # 重复次数（如 3 件）
base_fee: float | None               # 基础费（元）
unit_price: float | None             # 单价（元/单位）
total_price: float | None            # 总价（元）
formula: str | None                  # 报价公式说明
```

**结果与决策**：
```python
candidate_equipment_ids: list[str]   # 初筛候选设备列表
selected_equipment_id: str | None    # 最终选中设备 ID
rejected_equipment: list[dict]       # 被筛设备：[{id, reason}, ...]
missing_fields: list[str]            # 未补齐的字段（中文标签）
blocking_reason: str | None          # 阻塞原因（若有）
standard_evidences: list[str]        # 标准证据（从标准提取的相关文本）
standard_match_notes: str | None     # 标准匹配说明
```

### 11.2 报价公式

```
总价 = (基础费 + 单价 × 计价数量) × 重复次数
```

其中：
- `pricing_quantity`：单次执行的计价量（如 `5 小时`）
- `repeat_count`：同一试验的重复次数或样品数（如 `3 件`）
- 若 `repeat_count` 为空，默认按 `1` 处理

### 11.3 标准补充对应字段

仅以下字段允许由标准推断（`STANDARD_FILLABLE_FIELDS`）：
```python
required_temp_min, required_temp_max,
required_humidity_min, required_humidity_max,
required_temp_change_rate,
required_freq_min, required_freq_max,
required_accel_min, required_accel_max,
required_displacement_min, required_displacement_max,
required_irradiance_min, required_irradiance_max,
required_water_temp_min, required_water_temp_max,
required_water_flow_min, required_water_flow_max
```

**禁止补充的字段**：
- 样品尺寸：`sample_length_mm` 等（必须来自用户或文档）
- 样品重量：`sample_weight_kg`（必须来自用户或文档）

---

## 12. 标准补充详细流程

标准补充发生在**设备初筛之后**，仅针对**缺失字段**。

### 12.1 流程步骤

1. **获取标准文件**：根据 `standard_codes` 查找本地 `data/cleaned_markdown/` 中的文件

2. **检索相关证据**：通过向量相似度或关键字在 Qdrant 中检索，返回 chunks

3. **范围定位**：找到最高分的三级标题（如 `5.1.3`）

4. **生成扩展链**：
   ```
   初始范围：5.1.3
   一次扩展：5.1.*  (同二级下的所有内容)
   二次扩展：5.*    (同一级下的所有内容)
   ```

5. **分轮补表**：
   - 第一轮：发送 `5.1.3` 范围的内容，补出字段移除
   - 第二轮（若仍有待补）：发送 `5.1.*` 中**新增的**内容（不重复 `5.1.3`）
   - 第三轮（若仍有待补）：发送 `5.*` 中**新增的**内容

### 12.2 增量发送规则

范围扩展时**不重复发送已发送过的块**：

```
第一轮：发送 chunks [1, 2, 3]（范围 5.1.3）
第二轮：范围扩展至 5.1.*
        → 获取所有 chunks [1, 2, 3, 4, 5, 6]
        → 去重后发送 [4, 5, 6]
```

---

## 13. 前端展示原则

### 13.1 保留展示

- 上传区：用户上传文件入口
- 运行状态：当前处理进度与阶段
- 阶段切换：5 个阶段的标签展示
- 结构化报价表：FormRow 列表及详情
- 匹配设备表：初筛后的候选设备（**已置顶**）
- 被筛除设备表：不符合条件的设备及原因
- 人工补录区：用户手工修改缺失字段

### 13.2 不展示

- 文档原文调试区
- 清洗后的 Markdown 文本
- 标准候选 JSON
- 决策轨迹原文
- 模型完整响应

---

## 14. 已实现能力总结

✅ **OCR 层**：PDF → Markdown（表格识别、标题保留）
✅ **清洗层**：Markdown 规范化清洗
✅ **建库层**：标题分块、向量化、Qdrant 存储、自适应降级、断点续传
✅ **向量检索**：按标准号过滤 + 范围扩展 + 增量发送
✅ **报价流程**：5 阶段完整流程 + 人工补录
✅ **设备筛选**：初筛 + 复筛（基于补充后的条件）
✅ **多格式文档**：Word、Excel、PDF、Image 四种格式
✅ **报价计算**：支持重复次数参与计算

---

## 15. 系统限制与约束

### 15.1 性能限制

- Qdrant 单机部署，32MB Payload 限制（已通过自适应降级克服）
- 向量维度固定 3072（Qwen3-Embedding）
- 后端同步长请求（无异步）

### 15.2 功能限制

- 标准来源仅本地库（无网络源）
- 温变速率多需从标准曲线推导（难以直接抽取唯一值）
- 样品尺寸不允许由标准推断

### 15.3 部署限制

- Qdrant 需本地可达（HTTP）
- LLM 服务需可达（调用 Qwen API）
- 集中式 GPU 处理（无分布式推理）

---

## 16. 后续优先级

### P0：稳定性

- ✅ OCR 增量同步
- ✅ 清洗增量同步
- ✅ 建库断点续传
- ✅ GPU 内存优化
- ✅ Qdrant 自适应降级
- 待：标准补充回归样例库
- 待：端到端测试

### P1：增强

- 温变速率推导规则
- 表格型标准解析增强
- 扫描版 PDF 的 OCR 可靠性提升
- 标准补充可观测性（日志增强）

### P2：演进

- 若 run 超时频繁，改异步任务 + 轮询
- Qdrant 集群部署
- 标准补充多源支持（网络标准库）

---

## 17. 快速参考

### 环境变量配置

见 `backend/common/config.py` 和各服务 `settings.py`

### 关键文件路径

| 文件 | 用途 |
|------|------|
| `backend/quote/models.py` | FormRow 定义 |
| `backend/quote/stages.py` | 5 个阶段常量 |
| `backend/quote/orchestrator.py` | 报价编排主逻辑 |
| `backend/indexing/splitter.py` | 标题分块器 |
| `backend/indexing/service.py` | 向量化 + 入库 |
| `backend/quote/standard/module.py` | 标准检索入口 |
| `backend/quote/quoter.py` | 设备筛选与报价计算 |

### HTTP 端点

**报价服务** (8000)：
- `POST /api/runs` — 创建新 run
- `GET /api/runs/{run_id}` — 获取 run 详情
- `POST /api/runs/{run_id}/resume` — 继续报价

**OCR 服务** (8001)：
- `POST /api/ocr/library/sync` — 增量同步
- `POST /api/ocr/library/rebuild` — 全量重建
- `GET /api/ocr/library/status` — 查询状态

**建库服务** (8002)：
- `POST /api/indexing/sync` — 增量建库
- `POST /api/indexing/rebuild` — 全量重建

**清洗服务** (8003)：
- `POST /api/cleaning/sync` — 增量清洗
- `POST /api/cleaning/rebuild` — 全量清洗
