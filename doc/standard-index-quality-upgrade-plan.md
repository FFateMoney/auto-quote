# 标准索引质量升级计划

## 1. 背景

当前标准索引链路已经具备基础能力：

- 能从本地标准 PDF 构建索引。
- 能按标准号找到候选标准文档。
- 能按章节切块并做本地检索。
- 能把命中的标准证据送入后续补表流程。

但近期抽查表明，索引质量存在明显短板：

- 部分 PDF 属于扫描件，`pypdf` 无法抽到有效文字，导致整份文档无法切块。
- 部分多语言 PDF 尤其是日文 PDF，虽然抽出了文本，但存在严重乱码，导致 chunk 可读性差。
- 当前 chunk 入库缺少质量门槛，低质量 chunk 也会被写入索引。
- 当前 embedding 为本地轻量哈希向量，跨语言语义能力有限，对乱码文本几乎没有纠错能力。

因此，需要设计一轮标准索引质量升级方案，优先提升“可抽取、可切块、可检索、可评估”四个方面的稳定性。

## 2. 目标

本次升级目标如下：

- 在索引前识别 PDF 类型，区分数字 PDF 与扫描件 PDF。
- 为扫描件提供 OCR 抽取兜底，避免整份文档因抽字失败而不可索引。
- 对 chunk 建立质量评分机制，避免大量低价值、乱码或空洞 chunk 进入索引。
- 替换为更强、更多语言友好的 embedding，提高中文、英文、日文混合场景下的召回质量。

## 3. 非目标

本轮先不做以下事项：

- 不引入重型向量数据库服务。
- 不做标准库之外的外部标准抓取。
- 不一次性重写整个标准检索链路。
- 不在第一阶段就要求所有历史标准重新达到同一质量水平。

## 4. 总体策略

整体升级按“先抽取，再筛选，后增强”的顺序推进：

```text
PDF 输入
  -> PDF 类型检测（数字 / 扫描 / 混合）
  -> 文字抽取（文本层 / OCR / 混合合并）
  -> 页级清洗
  -> 章节切块
  -> chunk 质量评分
  -> 根据分数决定是否入库
  -> embedding 生成
  -> 本地检索使用
```

这样做的原因是：

- 如果抽取层质量不稳定，后面的 chunk 和 embedding 再强也救不回来。
- 如果没有入库筛选，低质量 chunk 会污染检索结果。
- 如果 embedding 过弱，多语言和表述变化会进一步放大召回问题。

## 5. 方案拆解

### 5.1 PDF 分流：检测数字 PDF 还是扫描件

#### 目标

在索引阶段为每份 PDF 打上抽取类型标签，为后续抽取策略提供依据。

#### 判断方向

建议综合以下信号：

- `pypdf.extract_text()` 是否能稳定抽到非空文本。
- 页面平均字符数是否达到最低阈值。
- 页面文本是否只包含极少量页码、目录符号或噪声。
- 页面中是否存在大量图片对象。
- 抽取文本中是否出现高比例异常字符、乱码字符或不可识别片段。

#### 初步分类

建议将 PDF 分类为三类：

- `digital_pdf`
  文字层质量足够，优先走文本抽取。
- `scanned_pdf`
  文字层不可用或几乎不可用，优先走 OCR。
- `hybrid_pdf`
  部分页可抽字，部分页不可抽字，按页选择文本抽取或 OCR。

#### 输出

建议在索引元数据中新增：

- `pdf_type`
- `text_extraction_mode`
- `page_text_stats`
- `suspected_encoding_issue`

## 5.2 扫描件 OCR

### 目标

为扫描件和混合型 PDF 提供 OCR 兜底，避免出现“整份标准无法切块”的情况。

### 处理策略

- 对 `scanned_pdf` 全量逐页 OCR。
- 对 `hybrid_pdf` 仅对文本层不足的页面做 OCR。
- 对 OCR 结果与文本层结果进行标准化与去重，避免同页文本被重复拼接。

### 推荐输出结构

每页保留以下中间结果：

- `raw_text_from_pdf`
- `raw_text_from_ocr`
- `merged_page_text`
- `page_extraction_source`

其中 `page_extraction_source` 可取值：

- `pdf_text`
- `ocr`
- `pdf_text+ocr`

### 注意事项

- OCR 结果应保留页码映射，避免证据定位丢失。
- 后续清洗逻辑需要区分 OCR 常见噪声，如误识别标点、拆字、重复行。
- OCR 开销较高，应支持只在必要时触发。

## 5.3 Chunk 质量评分与入库决策

### 目标

给每个 chunk 打一个质量分，并基于分数决定是否入库，减少低质量 chunk 对检索结果的污染。

### 评分维度

建议从以下维度计算 chunk 质量：

- 文本长度
- 可识别字符占比
- 乱码字符占比
- 数字和目录符号占比
- 是否存在有效章节标题
- 是否包含自然语言词序列
- 是否仅由页码、目录点线、版本信息组成
- 文本来源可信度
  例如 `pdf_text` 通常高于低质量 OCR，但高质量 OCR 可以高于乱码文本层

### 建议评分区间

- `score >= 0.8`
  高质量，直接入库
- `0.5 <= score < 0.8`
  可疑质量，允许入库但打标
- `score < 0.5`
  默认不入库

### 建议标签

为 chunk 增加以下质量标签：

- `quality_score`
- `quality_level`
- `quality_reasons`
- `ingest_decision`

其中 `ingest_decision` 可取值：

- `accepted`
- `accepted_with_warning`
- `rejected`

### 实施建议

- 第一阶段先做规则打分，不依赖模型。
- 评分结果写入 debug 产物，便于人工抽查。
- 低质量 chunk 不直接删除，可先保留在 debug 或 quarantine 目录中，方便复盘。

## 5.4 更强、更多语言友好的 embedding

### 目标

提升中文、英文、日文以及混合文档的检索质量，降低当前轻量哈希向量在多语言场景下的局限。

### 当前问题

当前 embedding 实现属于本地哈希向量方案，特点是：

- 本地执行成本低。
- 无需外部模型依赖。
- 但语义能力有限。
- 对多语言支持不足。
- 对乱码文本没有鲁棒性。

### 升级方向

新 embedding 方案应尽量满足：

- 支持中文、英文、日文等多语言。
- 对短句、标题、条款类文本有较稳定表现。
- 支持本地缓存与批量计算。
- 支持索引增量更新。
- 在资源可接受范围内运行。

### 适配建议

建议将 embedding 实现改为可插拔：

- `hash_embedding`
- `multilingual_embedding`

在配置中允许切换：

- `embedding_provider`
- `embedding_model`
- `embedding_batch_size`

### 迁移建议

- 新旧 embedding 先并行一段时间。
- debug 产物中保留检索对比结果。
- 在确认多语言召回改善后，再把旧方案降级为 fallback。

## 5.5 推进 Checklist

以下 checklist 以当前仓库代码为准，可直接用于推进和验收。

### 抽取层治理

- [x] 抽离通用 `packages/integrations/pdf_classifier.py`
- [x] 保留标准库批量分类包装器 `packages/integrations/standard_pdf_classifier.py`
- [ ] 将 PDF 分类结果正式接入 `StandardIndexer`
- [ ] 将文档级 `pdf_type / text_extraction_mode / suspected_encoding_issue` 写入索引元数据
- [ ] 为 `scanned_pdf` 增加整页 OCR fallback
- [ ] 为 `hybrid_pdf` 增加按页 OCR fallback
- [ ] 保留 `raw_text_from_pdf`
- [ ] 保留 `raw_text_from_ocr`
- [ ] 保留 `merged_page_text`
- [ ] 保留 `page_extraction_source`
- [ ] 将页级抽取统计写入 debug 产物

### 质量层治理

- [ ] 为 chunk 增加 `quality_score`
- [ ] 为 chunk 增加 `quality_level`
- [ ] 为 chunk 增加 `quality_reasons`
- [ ] 为 chunk 增加 `ingest_decision`
- [ ] 建立入库阈值与拒收逻辑
- [ ] 为低质量 chunk 保留 debug 或 quarantine 产物
- [ ] 输出 `chunk_quality_report.json`

### 向量层升级

- [ ] 将 embedding 改为可配置 provider
- [ ] 增加 `embedding_provider` 配置
- [ ] 增加 `embedding_model` 配置
- [ ] 增加 `embedding_batch_size` 配置
- [ ] 接入 `multilingual_embedding`
- [ ] 保留旧 `hash_embedding` 作为 fallback
- [ ] 输出新旧 embedding 检索对比样本

### 集成与验收

- [ ] 扫描件 PDF 不再大面积出现空页文本
- [ ] 混合型 PDF 的非空页覆盖率提升
- [ ] `chunk_preview.json` 中空 chunk 和纯噪声 chunk 比例下降
- [ ] 多语言文档召回排序质量提升
- [ ] 错误命中目录、页眉页脚、修订记录的比例下降

## 6. 实施顺序

建议按以下顺序推进，避免同时改太多层：

### 第一阶段：抽取层治理

- 新增 PDF 类型检测。
- 为扫描件和混合 PDF 引入 OCR fallback。
- 保留抽取来源和页级统计信息。

目标：

- 解决完全抽不到文字的问题。
- 解决部分页为空导致整份文档不可切块的问题。

### 第二阶段：质量层治理

- 为 chunk 增加质量评分。
- 建立入库阈值与拒收逻辑。
- 增加 debug 产物和人工抽查能力。

目标：

- 让索引库先变干净，减少错误召回。

### 第三阶段：向量层升级

- 替换为更强的多语言 embedding。
- 补充批量生成、缓存和切换配置。
- 做新旧 embedding 对比测试。

目标：

- 提升多语言检索与相似表达召回能力。

## 7. 数据结构建议

建议为文档和 chunk 增加以下字段。

### 文档级

- `pdf_type`
- `text_extraction_mode`
- `ocr_page_count`
- `pdf_text_page_count`
- `hybrid_page_count`
- `suspected_encoding_issue`
- `document_quality_score`

### chunk 级

- `text_source`
- `quality_score`
- `quality_level`
- `quality_reasons`
- `ingest_decision`
- `language_guess`

## 8. Debug 与观测

为了让后续调优可持续，建议扩展 debug 产物：

- `pdf_analysis.json`
  记录 PDF 类型判定过程与页级统计
- `page_extraction_report.json`
  记录每页使用了文本层还是 OCR
- `chunk_quality_report.json`
  记录每个 chunk 的质量分、拒收原因
- `retrieval_eval_samples.json`
  记录抽样检索效果，便于对比 embedding 升级前后差异

## 9. 验收标准

本计划建议使用以下指标做验收。

### 抽取层

- 扫描件 PDF 不再大面积出现空页文本。
- 混合型 PDF 的非空页覆盖率显著提升。
- 日文、英文、中文标准中，明显乱码文档占比下降。

### chunk 层

- `chunk_preview.json` 中空 chunk 和纯噪声 chunk 比例下降。
- 标题可读性明显提升。
- 被拒绝入库的 chunk 具备可解释原因。

### 检索层

- 标准试验章节命中率提升。
- 多语言文档召回排序质量提升。
- 错误命中目录、页眉页脚、修订记录的比例下降。

## 10. 风险与应对

### OCR 成本增加

风险：

- 全量 OCR 会显著增加索引时间。

应对：

- 先做 PDF 分流。
- 仅对扫描件或低质量页面触发 OCR。

### 多语言 embedding 引入复杂度

风险：

- 可能增加依赖、模型体积和构建时间。

应对：

- embedding 做成可配置、可回退。
- 保留旧方案作为 fallback。

### 质量阈值过严导致信息损失

风险：

- 有价值但格式差的 chunk 可能被误拒。

应对：

- 第一版采用“拒收入库但保留 debug 产物”的方式。
- 通过抽样复盘逐步调整阈值。

## 11. 里程碑建议

### M1：抽取分流与 OCR fallback

- 能识别数字 PDF、扫描 PDF、混合 PDF
- 扫描件具备可用文本产出

### M2：chunk 质量评分与入库决策

- 低质量 chunk 不再默认全部入库
- debug 产物可解释

### M3：embedding 升级与对比验证

- 新旧 embedding 支持切换
- 多语言样本上召回质量明显改善

## 12. 结论

本计划的核心思路不是只替换 embedding，而是先修复抽取层，再治理入库质量，最后升级语义表示能力。

执行顺序应保持为：

1. 先分流 PDF 类型
2. 再为扫描件补 OCR
3. 再对 chunk 做质量评分和入库决策
4. 最后替换为更强的多语言 embedding

这样可以确保后续优化建立在更稳定、更可解释的数据基础上。
