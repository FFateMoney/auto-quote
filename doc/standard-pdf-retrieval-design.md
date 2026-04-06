# 标准 PDF 检索与抽取设计方案

## 1. 背景

当前系统在“标准补充”阶段会先根据 `standard_codes` 在本地标准库中找到标准文件，再将整份标准文档重新预处理后发送给大模型补表。

这一做法在标准文件较短时可以工作，但对企业标准和行业标准的真实场景存在明显问题：

- 单份 PDF 往往有几十到上百页。
- 一个标准文件内通常包含多类试验项目，例如高温、低温、湿热、振动、盐雾、防尘、防水等。
- 模型需要同时完成“定位相关试验条目”和“抽取结构化字段”两件事，容易误召回相邻但不相同的试验。
- 发送整份 PDF 会显著增加 token 和多模态输入成本，响应速度也会变慢。
- 当前 PDF 图片做了 OCR，但 OCR 结果没有形成稳定的结构化检索资产，导致扫描版 PDF 的可用性不足。

结合 `standards/企业标准` 中的实际样本：

- `Q-JLY J7111029E-2024-汽车电气和电子零部件通用技术规范.pdf` 共 137 页，内部包含成体系的气候负荷、机械负荷、化学负荷等试验章节。
- `DAIMLER-MBN-10306(2020).pdf` 共 104 页，章节结构清晰，试验项按目的、参数、方法、要求组织。
- `En_26010NDS00_30.0_IP3.pdf` 共 71 页，既有目录型章节，又有表格型试验条目。

因此，标准补充阶段应从“整本送模”调整为“先检索定位，再定向抽取”。

## 2. 设计目标

### 2.1 目标

- 在本地标准库基础上建立可检索的标准知识索引。
- 以 `standard_codes` 为主过滤条件，在对应标准文档内部定位最相关的试验章节或条目。
- 只将命中的少量标准片段发送给大模型进行补表。
- 为模型输出保留证据出处，支持页码、章节号、标准号追溯。
- 保持与当前五阶段主流程兼容，尽量减少对外 API 的改动。

### 2.2 非目标

- 第一版不做外网标准爬取。
- 第一版不做跨仓库共享的通用知识库服务。
- 第一版不追求替换现有全部 PDF 预处理逻辑。
- 第一版不要求一次性引入重型向量数据库集群。

## 3. 总体方案

方案采用“章节感知的混合检索 + 分层证据判定 + 证据抽取”。

在系统边界上，标准本地 PDF 检索应被视为一个独立模块，而不是散落在文件路由、内核匹配和模型请求器中的若干零碎步骤。

整体流程如下：

```text
标准 PDF 离线建索引
  -> 文本抽取 / OCR 补偿
  -> 页级清洗
  -> 章节/条目切块
  -> 关键词索引 + embedding 索引 + 元数据索引

在线标准补充
  -> 根据 FormRow.standard_codes 找到候选标准文档
  -> 根据 raw_test_type / conditions_text / 已有字段构造查询
  -> 在候选标准内做混合召回
  -> 只选三级标题作为首轮种子片段
  -> 将种子片段送给模型判断“当前上下文是否足够报价”
  -> 若模型返回不足，则最多向上扩展两次，依次补到二级/一级标题
  -> 若任一轮断链、片段异常或模型仍判不足，则按“本地无标准”处理
  -> 仅当模型确认足够时，才将最终证据片段送给大模型补表
  -> 回写字段与证据来源
```

核心原则：

- 先缩小文档范围，再做文档内检索。
- 先定位试验章节，再由模型确认上下文是否足够，最后再抽字段。
- 检索层尽量输出结构化证据，而不是长篇原文。
- 不依赖单一向量检索，而是融合关键词、标题、元数据和 embedding。
- 标准检索模块对外只暴露少量清晰接口，前置文件路由和后置模型补表都不感知其内部细节。
- 检索失败、结构断链、上下文不足统一收敛为“本地无标准”语义，不允许回退整本 PDF。

## 4. 为什么不是纯向量库

标准文档与普通问答语料不同，具有很强的结构特征：

- 存在稳定的标准号、章节号、试验名称。
- 同一类试验名称相似度高，例如“高温储存试验”和“高温工作试验”语义接近但参数不同。
- 大量关键条件是显式数值，如 `-40℃`、`96h`、`93%RH`、`2 cycles`。
- 很多条目带有固定中英双语标题和表格标签。

因此第一版更适合采用混合检索：

- 元数据过滤：按 `standard_code`、文档路径、标准类别过滤。
- 关键词检索：按试验名、同义词、字段词、章节号召回。
- 向量检索：解决中英混排、表述不统一、句式变化问题。
- rerank：综合标题命中、关键字段命中和语义相似度进行排序。

## 5. 系统组件设计

建议在现有 `packages/integrations/` 下新增一个标准检索子系统，并以单一门面模块对外暴露能力。

```text
packages/integrations/
├── standard_library.py            # 保留：按标准号找文件
├── standard_indexer.py            # 新增：离线索引构建
├── standard_retriever.py          # 新增：在线混合检索
├── standard_retrieval_module.py   # 新增：标准检索门面模块
├── standard_resolution.py         # 新增：分层证据解析状态机
├── standard_context_judge.py      # 新增：上下文充分性判定
├── standard_chunker.py            # 新增：章节/条目切块
├── standard_cleaner.py            # 新增：页眉页脚/水印清洗
├── standard_store.py              # 新增：索引文件读写
└── embeddings.py                  # 新增：embedding 适配与缓存
```

同时在 `packages/core/` 中增加标准证据对象和新的补表入口：

```text
packages/core/
├── models.py                      # 新增 StandardChunk / StandardEvidence
├── kernel.py                      # 新增 resolve_standard_evidences()
└── orchestrator.py                # 标准阶段改为“检索后补表”
```

### 5.1 模块边界

整个系统建议保持以下边界：

- 文件路由模块：
  - 负责用户上传文件的识别、预处理和初始 `FormRow` 抽取。
  - 不关心本地标准索引是否存在、如何切块、如何检索。
- 标准检索模块：
  - 负责标准索引维护和标准证据召回。
  - 不关心上传文档如何被路由，也不负责调用大模型。
- 模型补表模块：
  - 负责消费当前表单与标准证据，组织 prompt，并调用模型补字段。
  - 不关心标准 PDF 是如何被切块和检索出来的。

这种分层下，标准检索模块内部可以保持轻量实现，但系统外部始终只依赖它的门面接口。

### 5.2 门面接口

标准检索模块建议对外只暴露以下门面方法：

- `sync_index(sync=True, rebuild=False) -> IndexBuildReport`
- `resolve_for_row(row: FormRow, run_dir: Path | None = None) -> StandardResolutionResult`
- `resolve_for_rows(rows: list[FormRow], run_dir: Path | None = None) -> dict[str, StandardResolutionResult]`

推荐由 `StandardRetrievalModule` 作为唯一对外入口。

内部的 `cleaner / chunker / store / embedder / retriever / resolution / judge` 视为模块内部实现细节，而不是系统级插件。

## 6. 数据模型

### 6.1 StandardDocumentRecord

表示一个已建索引的标准文档。

建议字段：

- `doc_id`
- `standard_key`
- `standard_code`
- `title`
- `path`
- `category`
- `language`
- `page_count`
- `file_hash`
- `indexed_at`
- `chunk_count`

### 6.2 StandardChunk

表示标准文档中的最小检索单元。

建议字段：

- `chunk_id`
- `doc_id`
- `standard_code`
- `path`
- `page_start`
- `page_end`
- `section_id`
- `section_title`
- `parent_section_id`
- `chunk_type`
- `text`
- `normalized_text`
- `keywords`
- `aliases`
- `embedding`

`chunk_type` 建议取值：

- `section`
- `subsection`
- `table_row`
- `page_fallback`

### 6.3 StandardEvidence

表示在线补表阶段提供给模型的证据片段。

建议字段：

- `chunk_id`
- `standard_code`
- `doc_title`
- `path`
- `page_start`
- `page_end`
- `section_id`
- `section_title`
- `score`
- `match_reasons`
- `text`

### 6.4 FormRow 扩展

在现有 `FormRow` 上建议增加以下字段：

- `standard_evidences: list[StandardEvidence] = []`
- `standard_match_notes: list[str] = []`

其中：

- `standard_evidences` 用于保存标准补表的证据来源。
- `standard_match_notes` 用于展示“为何命中该标准片段”。

## 7. 离线建索引方案

### 7.1 触发方式

标准索引不应绑定在日常运行主流程中，也不应放在可随时清空的 `runtime/` 下。

建议提供两种维护方式：

- 显式执行增量同步：
  - `python -m packages.integrations.standard_indexer --sync`
- 显式执行全量重建：
  - `python -m packages.integrations.standard_indexer --rebuild`

建议行为：

- 服务启动时只加载索引清单和元数据，不自动重建索引。
- 当检测到某个标准文件尚未建索引时，只记录“索引缺失”状态，不阻塞主流程。
- 索引的补齐由独立命令或后台任务完成。
- 增量同步只处理新增、修改和缺失的标准文件，不重新处理全部标准库。

### 7.2 文本来源

标准 PDF 的文本来源按优先级处理：

1. `pypdf` 提取原生文字。
2. 若页文本过少或判定为扫描页，则对整页或页内图片执行 OCR。
3. 将 OCR 文本与原生文本融合为页级文本资产。

建议新增页级对象：

- `page_num`
- `raw_text`
- `ocr_text`
- `merged_text`
- `image_count`
- `is_scanned_like`

### 7.3 页级清洗

在建索引前需要对页级文本做清洗，避免重复噪声污染检索。

清洗规则建议包括：

- 去页眉页脚。
- 去重复页码。
- 去重复公司抬头。
- 去双语重复空行。
- 去固定水印字段，例如样本中出现的 `TO / OF / BY / AT` 串。
- 合并断行和异常空白。

建议将清洗前后的文本都保留到索引中，便于调试。

### 7.4 结构化切块

第一版不建议按固定字符数硬切，而应优先按文档结构切块。

#### 7.4.1 章节切块

优先识别如下模式：

- `5.3.3 高温储存试验`
- `5.3.3.1 试验目的`
- `8.4 M-04 Vibration test`
- `4-6-2 Water spray test`
- `VI/07 Random vibration durability test`

可采用正则加启发式规则：

- 纯数字章节：`^\d+(\.\d+){1,4}`
- 连字符章节：`^\d+-\d+(-\d+)?`
- 代号章节：`^[A-Z]{1,4}/\d{2}`
- 中英双语标题同列识别

#### 7.4.2 邻接合并

对以下内容可自动归并到同一试验单元：

- `试验目的`
- `试验参数`
- `试验方法`
- `技术要求`

例如：

- `5.3.3.1` 至 `5.3.3.4` 可组成一个聚合试验单元 `5.3.3 高温储存试验`。

#### 7.4.3 回退切块

若文档结构难以识别，则降级为：

- 按页切块
- 或按固定大小窗口切块，例如 `800-1200` 中文字符，重叠 `150-200`

但这仅作为兜底策略。

### 7.5 关键词提取

为每个 chunk 提取检索友好的关键词。

关键词来源：

- 标题词
- 试验名词典
- 数值条件词
- 标准中已出现的关键术语

例如：

- `高温储存试验`
- `高温工作试验`
- `低温储存`
- `盐雾`
- `防水`
- `IPX9K`
- `湿热`
- `温度循环`
- `振动`
- `冲击`

### 7.6 embedding

每个 chunk 生成一个 embedding，并缓存到本地索引。

要求：

- 支持中英混排。
- 结果可缓存，避免重复生成。
- 文件未变化时不重复计算。

第一版不强依赖专门数据库，可以先将 embedding 存为本地文件。

## 8. 在线检索方案

### 8.1 查询构造

针对每一条 `FormRow` 构造检索查询。

输入来源：

- `raw_test_type`
- `canonical_test_type`
- `standard_codes`
- `conditions_text`
- `sample_info_text`
- 已抽取出的数值字段

输出结构：

- `query_text`
- `keyword_terms`
- `numeric_terms`
- `preferred_section_terms`

例如：

- `raw_test_type=高温试验`
- `conditions_text=85C 24h`

可构造成：

- 查询主文本：`高温试验 高温工作 高温储存 85C 24h`
- 偏好词：`试验参数 试验方法 技术要求`

### 8.2 文档过滤

优先按 `standard_codes` 过滤。

逻辑：

- 若 `standard_codes` 非空，则只在对应标准文档内检索。
- 若多个标准号同时存在，则分别检索后合并结果。
- 若没有标准号，则可降级为在全库中按试验名检索，但第一版可直接跳过。

### 8.3 混合召回

每个候选文档内执行三路召回：

- 标题召回：章节标题、条目标题、别名词匹配。
- 关键词召回：BM25 或轻量倒排索引。
- 向量召回：embedding 相似度检索。

每路召回取前若干条，再合并去重。

### 8.4 rerank

对召回结果进行打分排序。

建议打分项：

- 标题精确命中
- 标题别名命中
- 关键词覆盖度
- 数值条件命中
- embedding 相似度
- 章节完整性

示例：

- `高温试验` 同时命中 `高温工作试验` 和 `高温储存试验` 时，若用户文本含“持续带电工作”，应提升 `高温工作试验` 的分数。
- 若用户文本含“存放 48h/504h”，应提升 `高温储存试验` 的分数。

### 8.5 邻近扩展

模型补表时往往需要完整上下文，因此检索命中后应自动扩展相邻块。

规则建议：

- 命中 `section` 时，带上其下属 `试验参数 / 方法 / 要求` 子块。
- 命中 `subsection` 时，回溯父节并补充同级关键子块。
- 命中表格条目时，可带上前后 1 个条目作为上下文。

### 8.6 输出数量控制

第一版建议：

- 每个 `FormRow` 最多返回 3 个主命中试验单元。
- 每个试验单元最多拼接 2 到 4 个子块。
- 最终送模文本总长度设置上限，例如 `8k-15k` 字符。

这样可以显著降低当前整本送模造成的开销。

### 8.7 分层证据判定协议

为避免仅靠本地规则预判“哪一级标题才是完整报价单元”，在线检索阶段引入一个严格受控的多轮范围扩展协议。

协议规则如下：

1. 本地检索阶段只选择三级标题 chunk 作为首轮种子片段。
2. 本地只选择得分最高的三级标题作为唯一种子片段，不并行尝试多个种子。
3. 范围扩展按固定链路进行：
   - 例如 `5.1.3 -> 5.1.* -> 5.*`
   - 例如 `4-6-2 -> 4-6-* -> 4-*`
4. 每一轮只把当前章节范围发送给模型，不发送整份标准。
5. 本轮如果补出了部分字段，就立即记录并从剩余待补字段中移除。
6. 若本轮仍有未补字段，则进入下一层章节范围；所有待补字段共享同一条扩展链和同一组扩展次数。
7. 进入下一层范围时，只发送“新增进入范围的章节内容”，不重复发送上一轮已经发送过的块。
   - 例如 `5.1.3 -> 5.1.*` 时，`5.1.*` 不再重复发送 `5.1.3`
   - 例如 `5.1.* -> 5.*` 时，`5.*` 只发送新进入的 `5.2 / 5.3 / 5.4 ...`
8. 最多只允许向上扩展两次，也就是最多扩到一级章节范围。
9. 任何异常都直接按“本地无标准”处理，不再请求更多内容：
   - 未命中三级标题
   - 找不到上一级章节范围
   - 上一级章节范围内容为空或明显残缺
   - 模型输出不合规
   - 到一级标题范围后仍然无法补出任何剩余字段

该协议的目标不是“只要有 PDF 就算找到了标准”，而是“只有成功定位到足够支撑报价的正确标准片段，才算找到本地标准”。

### 8.8 为什么采用范围扩展

这样设计有几个好处：

- 首轮默认发送三级标题，token 更省，也更接近最小可用上下文。
- 所有待补字段共享同一条扩展链，避免不同字段各自触发重复请求。
- 每轮只保留“仍未补出的字段”，能补的立即落表，不会因为别的字段没补出而整体失败。
- 上探时发送的是章节范围，而不是孤立父节，更符合标准文档的实际组织方式。
- 扩展轮次被严格限制，避免再次退化为“整本送模”。
- 失败语义统一，外层业务不需要关心是“没找到标准”还是“找到了但上下文不足”。

## 9. 模型补表方案

### 9.1 输入形式

标准补表阶段不再传入整份 `NormalizedDocument`，而是传入：

- 当前表单行
- 已命中的标准证据片段
- 每个片段的标准号、章节号、页码、匹配原因

建议核心请求器方法保留为：

- `QwenRequester.enrich_form_with_evidences(rows, run_dir)`

其中补表接口每一轮都收到“本轮剩余目标字段”，例如湿度、温变速率、位移等；模型只需要尝试补出本轮能从当前章节范围确认的字段，补不出的字段留给下一轮范围扩展。

### 9.2 prompt 结构

补表 prompt 建议包含以下部分：

- 当前表单
- 本次目标：仅补充已有行，不新增重复项目
- 证据片段清单
- 证据正文
- 输出 schema
- 规则

规则应强调：

- 只允许依据证据片段填写，不要凭经验补充。
- 如果证据存在多种候选试验，应保留不确定性，不要强行二选一。
- 输出时尽量保留 `row_id`。
- 如能确定来源，应在 `standard_evidences` 中回写出处。

补表 prompt 必须明确约束：

- 只允许补充本轮剩余目标字段
- 不允许请求整本标准
- 当前章节范围无法支撑的字段保持为空
- 当前轮未补出的字段由本地系统决定是否扩到下一层章节范围

### 9.3 输出形式

模型输出仍保持 `items` 结构，但建议增加证据字段：

- `matched_standard_code`
- `matched_section_id`
- `matched_section_title`
- `evidence_pages`

若不希望扩大主表字段，也可以只在本地 merge 时自动附加证据对象。

## 10. 与现有代码的集成方式

### 10.1 保留现有 StandardLibrary 的职责

当前 [standard_library.py](/my_storage/chen/auto-quote/packages/integrations/standard_library.py) 负责按标准号找到文件路径。

建议保留该职责，并将标准检索能力统一收敛到门面模块中。各组件职责如下：

- `find_docs_by_codes(codes) -> list[StandardDocumentRecord]`
- `StandardRetrievalModule.sync_index(...)`
- `StandardRetrievalModule.resolve_for_rows(...)`

其中：

- `StandardLibrary` 只负责标准文件定位与索引文档发现。
- `StandardRetrievalModule` 负责组合索引器、在线检索器、上下文判定器和分层解析状态机。
- `LocalKernel` 只负责调用门面模块并把证据回写到 `FormRow`。

当前匹配规则建议进一步收敛为：

- 入库时为每个标准生成统一的 `standard_key`
- `standard_key` 规则：
  - 只按顺序保留英文字母和数字
  - 全部转小写
  - 中文、空格、符号、扩展名全部去掉
- 索引文件命名统一使用该 key：
  - `docs/<standard_key>.json`
  - `chunks/<standard_key>.jsonl`
  - `embeddings/<standard_key>.npy`
- 查询时只需要对用户传入的标准号做同样的规范化，再与 `standard_key` 做精确匹配

这样可以把“文件名脏字符清洗”前移到入库阶段，避免查询时反复扫描和动态处理文件名。

### 10.2 调整标准阶段编排

当前系统完成接入后，标准阶段统一改为：

1. `match_test_types()`
2. `select_equipment()`，先暴露真实缺失字段
3. `attach_standard_refs()`
4. `kernel.resolve_standard_evidences(rows, run_dir)`
5. `requester.enrich_form_with_evidences(rows)`
6. `select_equipment()`，基于补字段结果重新筛选设备

这样：

- 标准补充不再作为前置盲补阶段，而是作为设备筛选后的定向补充阶段。
- 仍保留标准文件关联记录。
- 不再把整份标准 PDF 重新预处理并发送给模型。
- 标准补充阶段先经过“证据充分性判定”，仅当判定成功时才执行补表。
- 模型只补设备筛选后暴露出的、且可由标准支撑的缺失字段。
- 标准补充阶段只允许“受控分层证据送模”这一条路径。

### 10.3 Quoter 触发条件调整为后置缺失字段驱动

[quoter.py](/my_storage/chen/auto-quote/packages/core/quoter.py) 中标准补充触发条件不再依赖前置抽取是否“看起来缺信息”，而是依赖设备筛选后暴露出的缺失字段。

变化仅在“如何补表”：

- 过去：整份标准送模。
- 现在：设备筛选后，仅针对可由标准支撑的缺失字段做命中片段送模。

## 11. 存储设计

第一版建议全部使用本地持久化文件存储，避免引入额外部署复杂度。

但该存储应与 `runtime/` 分离，因为：

- `runtime/` 是运行态临时产物目录，允许被清空。
- 标准索引属于知识资产，应该长期保留。
- 标准索引需要支持增量更新、缺失补齐和跨多次运行复用。

建议新增独立配置项：

- `integrations.standard_index_dir`

默认路径建议为：

- `data/standard_index/`

这样它仍位于项目内，便于备份和迁移，但不会与运行时产物混淆。

```text
data/standard_index/
├── manifest.json                  # 文档级索引清单
├── docs/
│   └── <doc_id>.json              # 文档元数据
├── chunks/
│   └── <doc_id>.jsonl             # chunk 列表
├── embeddings/
│   └── <doc_id>.npy               # 向量缓存
├── cache/
│   ├── file_hashes.json           # 文件 hash 与增量更新信息
│   └── missing_index.json         # 缺失索引登记
└── debug/
    └── <doc_id>/
        ├── cleaned_pages.json     # 清洗后的页文本
        └── chunk_preview.json     # 切块调试结果
```

优点：

- 易调试
- 易备份
- 无需额外服务
- 适合当前仓库规模
- 可以独立于运行目录长期保留
- 支持按文件 hash 做增量同步
- 支持登记“哪些标准尚未完成索引”

当标准库规模明显扩大后，再升级到 SQLite / pgvector / 专用向量库也不迟。

### 11.1 为什么第一版不用数据库

当前更适合先采用文件化索引，而不是数据库，原因如下：

- 标准库来源本身就是本地文件系统。
- 当前首要任务是提升可观察性和可调试性，而不是复杂查询能力。
- 章节切块和清洗策略还在演进期，文件化格式更便于反复重建和检查。
- 已有流程有 `standard_codes` 作为强过滤条件，第一版在线检索通常只需加载少量文档索引。

推荐文件格式：

- 文档元数据：`JSON`
- chunk 列表：`JSONL`
- embedding：`NPY`

其中：

- `JSONL` 便于逐条查看 chunk 内容。
- `NPY` 便于高效加载向量矩阵并做相似度计算。

### 11.2 未来升级到数据库的时机

当出现以下情况时，再考虑升级到数据库或向量库：

- 标准文档数量达到数百到上千份。
- chunk 总量明显增大，单机文件扫描和加载开始变慢。
- 需要多人并发维护索引。
- 需要复杂全文检索、管理后台或统计分析。

推荐升级顺序：

1. 本地文件索引
2. SQLite + FTS
3. PostgreSQL / pgvector 或专用向量库

## 12. 实现步骤

### 12.1 MVP 阶段

目标：先从“整本送模”切换到“按标准号过滤后检索章节，再经过分层判定后送模”。

实现范围：

- 支持 PDF 文本抽取
- 支持页级清洗
- 支持章节切块
- 支持关键词召回
- 支持简单向量召回
- 支持三级标题起步的分层证据判定
- 支持标准证据送模

暂不做：

- 复杂表格重建
- 全库无标准号检索
- 动态反馈学习

### 12.2 第二阶段

- 增加扫描页 OCR 融合
- 增加 rerank
- 增加邻近章节自动拼接
- 增加命中结果可视化

### 12.3 第三阶段

- 支持标准内多行联合推断
- 支持跨标准对照
- 支持人工确认命中章节后再补表

## 13. 失败回退策略

为控制改造风险，建议统一采用以下失败语义：

- 若标准未建索引：按“本地无标准”处理。
- 若未命中三级标题：按“本地无标准”处理。
- 若分层判定时上一级章节范围断链：按“本地无标准”处理。
- 若模型判定输出不合规：按“本地无标准”处理。
- 若到一级标题后仍不足：按“本地无标准”处理。
- 若补表失败：继续保留当前 `waiting_manual_input` 分支。

## 14. 风险与应对

### 14.1 章节识别不稳

风险：

- 不同企业标准格式差异大，章节模式未必统一。

应对：

- 多模式正则识别
- 失败时退回页级切块
- 保留调试导出文件

### 14.2 OCR 噪声影响检索

风险：

- 扫描版 PDF 的 OCR 可能引入乱码或错字。

应对：

- OCR 文本单独存储
- 检索时降低 OCR 来源权重
- 仅在原生文本缺失时强依赖 OCR

### 14.3 高相似试验误命中

风险：

- “高温储存”和“高温工作”这类项目容易混淆。

应对：

- 强化标题命中权重
- 引入工作模式、时长、是否带电等判别词
- 保留多个三级候选，并逐个执行受控分层判定

### 14.4 系统复杂度上升

风险：

- 建索引、检索、补表链路比当前更复杂。

应对：

- 第一版只做本地文件索引
- 不保留整本送模兜底
- 日志中输出每次命中的三级候选、上探路径与最终判定

## 15. 推荐落地顺序

建议按以下顺序推进：

1. 先实现页级清洗和章节切块。
2. 再实现本地索引文件格式和增量更新。
3. 然后实现按 `standard_codes` 过滤后的关键词检索。
4. 接着补充 embedding 检索和 rerank。
5. 最后替换标准补表 prompt 与编排逻辑。

这样可以在每一步都获得可观收益，不必等完整知识库完成后才看到效果。

## 16. 结论

当前标准补充链路的主要问题，不在于模型能力不够，而在于给模型的上下文组织方式不适合长篇标准文档。

更适合本项目的方案是：

- 继续使用本地标准库。
- 保留按标准号找文件的现有能力。
- 新增“离线切块建索引 + 在线混合检索 + 证据送模”的中间层。
- 将标准补表从“整本阅读”改为“命中片段定向抽取”。

这一方案可以同时改善：

- token 成本
- 响应速度
- 命中准确率
- 结果可解释性
- 扫描版 PDF 的利用率

并且能够在不大幅改动现有 API 和前后端交互的前提下，逐步演进落地。

## 17. 实施清单

本节给出面向当前仓库的具体落地清单。建议按阶段推进，每一阶段都保证“可运行、可验证、可回退”。

### 17.1 配置与目录

#### 17.1.1 修改配置项

需要修改：

- `config.yaml`
- `packages/integrations/settings.py`

需要新增的配置项：

- `integrations.standard_index_dir`
- `integrations.standard_index_enable`
- `integrations.standard_index_debug`
- `integrations.standard_retrieval_top_k`
- `integrations.standard_retrieval_expand_neighbors`

建议默认值：

- `standard_index_dir: data/standard_index`
- `standard_index_enable: true`
- `standard_index_debug: true`
- `standard_retrieval_top_k: 5`
- `standard_retrieval_expand_neighbors: true`

验收标准：

- 不配置新项时系统有合理默认值。
- 可通过环境变量覆盖。
- 服务启动时能够读取并打印索引目录配置。

#### 17.1.2 初始化持久化目录

需要新增目录约定：

```text
data/standard_index/
├── manifest.json
├── docs/
├── chunks/
├── embeddings/
├── cache/
└── debug/
```

实现要求：

- 应由索引构建脚本初始化。
- 主服务仅读取，不负责创建完整索引内容。

### 17.2 数据模型

#### 17.2.1 扩展核心模型

需要修改：

- `packages/core/models.py`

需要新增模型：

- `StandardDocumentRecord`
- `StandardChunk`
- `StandardEvidence`
- `StandardIndexManifest`

建议字段：

- `StandardDocumentRecord`：文档级元数据
- `StandardChunk`：切块与检索单元
- `StandardEvidence`：送模证据对象
- `StandardIndexManifest`：全局索引清单

同时扩展 `FormRow`：

- `standard_evidences`
- `standard_match_notes`

验收标准：

- 新模型可正常序列化与反序列化。
- `run_state.json` 可兼容新字段。
- 不使用标准检索时，新增字段默认空值。

### 17.3 离线索引构建

#### 17.3.1 新增标准清洗器

需要新增：

- `packages/integrations/standard_cleaner.py`

职责：

- 清洗页眉页脚
- 删除重复水印
- 归一化空白与断行
- 输出清洗前后页文本

建议接口：

- `clean_page_text(text: str) -> str`
- `clean_document_pages(pages: list[str]) -> list[str]`

验收标准：

- 对吉利标准样本能去除重复 `TO / OF / BY / AT` 字样。
- 不破坏章节标题和正文内容。

#### 17.3.2 新增标准切块器

需要新增：

- `packages/integrations/standard_chunker.py`

职责：

- 识别章节标题
- 按章节切块
- 聚合同一试验单元的参数、方法、要求
- 无法识别时回退到页级切块

建议接口：

- `chunk_document(doc: StandardDocumentRecord, pages: list[str]) -> list[StandardChunk]`

第一版需支持的标题模式：

- `5.3.3`
- `5.3.3.1`
- `8.4`
- `4-6-2`
- `VI/07`

验收标准：

- `Q-JLY...pdf` 能切出 `5.3.1`、`5.3.2`、`5.3.3`、`5.3.9`、`5.3.15` 等试验节。
- `DAIMLER-MBN-10306(2020).pdf` 能切出 `8.4 M-04 Vibration test`、`9.6 K-06 Salt spray testing`。
- `En_26010NDS00_30.0_IP3.pdf` 至少能切出 `4-6-2`、`4-6-4`、`VI/07` 等条目或回退块。

#### 17.3.3 新增索引存储层

需要新增：

- `packages/integrations/standard_store.py`

职责：

- 写入 `manifest.json`
- 写入 `docs/<doc_id>.json`
- 写入 `chunks/<doc_id>.jsonl`
- 写入 `embeddings/<doc_id>.npy`
- 维护 `cache/file_hashes.json`
- 维护 `cache/missing_index.json`

建议接口：

- `save_document_record(record)`
- `save_chunks(doc_id, chunks)`
- `save_embeddings(doc_id, matrix)`
- `load_manifest()`
- `load_chunks(doc_id)`
- `load_embeddings(doc_id)`
- `mark_missing(path, reason)`

验收标准：

- 单个文档可独立读写。
- 重复运行 `--sync` 不会重复写入未变化文件。
- 文档删除或重命名时能检测到孤儿索引并记录。

#### 17.3.4 新增 embedding 适配层

需要新增：

- `packages/integrations/embeddings.py`

职责：

- 统一 embedding 模型调用
- 管理本地向量缓存
- 提供批量编码接口

建议接口：

- `embed_texts(texts: list[str]) -> list[list[float]]`
- `embed_query(text: str) -> list[float]`

验收标准：

- 相同文本重复编码时可复用缓存。
- 向量维度稳定一致。
- 编码失败时有明确错误日志。

#### 17.3.5 新增索引器入口

需要新增：

- `packages/integrations/standard_indexer.py`

职责：

- 扫描 `standards/`
- 计算文件 hash
- 判断新增、修改、缺失文件
- 调用清洗器、切块器、embedding 适配器、存储层
- 支持 `--sync` 与 `--rebuild`

建议接口：

- `build_index(sync: bool = True, rebuild: bool = False) -> IndexBuildReport`

命令示例：

- `python -m packages.integrations.standard_indexer --sync`
- `python -m packages.integrations.standard_indexer --rebuild`

验收标准：

- 新增一个 PDF 后执行 `--sync` 只处理新文件。
- 修改一个 PDF 后执行 `--sync` 只重建该文件。
- 删除索引目录后执行 `--rebuild` 能完整恢复。

### 17.4 在线检索

#### 17.4.1 扩展标准库入口

需要修改：

- `packages/integrations/standard_library.py`

保留原有能力：

- `find_by_codes()`

新增能力：

- `find_docs_by_codes()`
- `list_indexed_docs()`
- `has_index_for_path()`

目标：

- 让“找文件”和“找索引文档”职责并存。

验收标准：

- 有标准文件但无索引时，能明确区分“文件存在”和“索引缺失”两种状态。

#### 17.4.2 新增在线检索器

需要新增：

- `packages/integrations/standard_retriever.py`

职责：

- 根据 `FormRow` 构造查询
- 先按 `standard_codes` 过滤文档
- 对候选文档执行关键词召回
- 对候选文档执行向量召回
- 混合打分并返回三级标题种子候选

建议接口：

- `retrieve_seed_candidates_for_row(row: FormRow) -> list[RetrievedChunkCandidate]`
- `load_chunks_for_doc(doc_id: str) -> list[StandardChunk]`
- `build_evidence(doc, chunk, score, reasons) -> StandardEvidence`

内部方法建议：

- `_build_query(row)`
- `_keyword_score(chunk, query)`
- `_vector_score(chunk, query_vector)`
- `_rerank(candidates)`
- `_expand_neighbors(chunks, doc_chunks)`

验收标准：

- 对“高温试验 + Q/JLY...”能够优先召回 `5.3.3` 或 `5.3.4` 相关块。
- 对“盐雾试验 + Q/JLY...”能够优先召回 `5.3.9`。
- 对“防水试验 + Q/JLY...”能够优先召回 `5.3.15`。

#### 17.4.3 新增分层解析状态机与门面模块

需要新增：

- `packages/integrations/standard_resolution.py`
- `packages/integrations/standard_context_judge.py`
- `packages/integrations/standard_retrieval_module.py`

职责：

- `standard_resolution.py` 负责“三级起步、最多上探两次、失败即无标准”的状态机
- `standard_context_judge.py` 负责与模型交互，只判断当前上下文是否足够
- `standard_retrieval_module.py` 封装 `StandardIndexer`、`StandardRetriever`、`StandardResolver`
- 对外提供单一入口
- 维持标准检索模块与其他系统模块之间的清晰边界

建议接口：

- `sync_index(sync=True, rebuild=False)`
- `resolve_for_row(row, run_dir=None)`
- `resolve_for_rows(rows, run_dir=None)`

验收标准：

- `LocalKernel` 与后续 `orchestrator` 只依赖门面模块，不直接依赖清洗器、切块器、存储层等内部组件。

### 17.5 内核与编排接入

#### 17.5.1 扩展 LocalKernel

需要修改：

- `packages/core/kernel.py`

建议新增方法：

- `resolve_standard_evidences(rows: list[FormRow], run_dir: str | None = None) -> tuple[list[FormRow], list[str]]`

职责：

- 读取每一行的标准号
- 调用 `StandardRetrievalModule`
- 将证据回写到 `FormRow.standard_evidences`
- 将失败说明统一回写到 `FormRow.standard_match_notes`
- 输出命中说明日志

验收标准：

- 每条表单行都能独立附带标准证据。
- 未命中时只记 note，不抛异常中断。

#### 17.5.2 改造标准补充阶段

需要修改：

- `packages/core/orchestrator.py`

当前逻辑：

- `match_test_types()`
- `select_equipment()`
- `attach_standard_refs()`
- `resolve_standard_evidences()`
- `requester.enrich_form_with_evidences()`
- `select_equipment()`

改造后逻辑：

- `match_test_types()`
- `select_equipment()`
- `attach_standard_refs()`
- `resolve_standard_evidences()`
- `requester.enrich_form_with_evidences()`
- `select_equipment()`

兼容策略：

- 当索引缺失、三级标题缺失、章节范围断链或模型判定失败时，统一按“当前信息继续报价”处理。

验收标准：

- 默认路径下标准补充阶段不再整本送模。
- 日志中可看到每行命中的标准章节和页码。

### 17.6 模型补表改造

#### 17.6.1 新增证据送模接口

需要修改：

- `packages/integrations/qwen_requester.py`
- `prompts.json`

新增方法：

- `enrich_form_with_evidences(current_rows, run_dir=None)`

新增 prompt：

- `standard_enrich_with_evidences`

输入结构建议包括：

- 当前表单
- 每一行对应的证据片段
- 证据来源章节与页码
- 输出 schema
- 严格规则

规则强调：

- 每轮只允许补充当前剩余目标字段
- 当前轮补出的字段立即落表并从剩余目标字段中移除
- 若仍有剩余字段，本地系统再扩到下一层章节范围
- 只能依据证据片段补字段
- 不得新增重复行
- 优先保留 `row_id`
- 无法确定时留空

验收标准：

- 模型请求文本明显短于“整本标准送模”。
- 结果可补齐 `conditions_text`、温湿度、时长等字段。
- 输出可追溯到具体章节和页码。

### 17.7 调试与运维脚本

#### 17.7.1 新增调试脚本

建议新增：

- `scripts/debug_standard_index.py`
- `scripts/debug_standard_retrieval.py`

用途：

- 查看某个 PDF 清洗后的页文本
- 查看某个 PDF 的切块结果
- 输入一组查询词，输出 top-k 命中块

验收标准：

- 不启动主服务也能单独调试索引和检索效果。

#### 17.7.2 新增最小验收命令

建议至少支持以下手工验收命令：

```bash
python -m packages.integrations.standard_indexer --sync
python scripts/debug_standard_retrieval.py --code "Q/JLY J7111029E-2024" --query "高温试验 85C 24h"
python scripts/debug_standard_retrieval.py --code "Q/JLY J7111029E-2024" --query "盐雾试验"
python scripts/debug_standard_retrieval.py --code "Q/JLY J7111029E-2024" --query "防水试验"
```

### 17.8 分阶段交付建议

#### 第一批

- 配置项
- 核心模型
- 标准清洗器
- 标准切块器
- 索引存储层
- `standard_indexer --sync`

交付结果：

- 能把 `standards/企业标准` 转成可读索引文件。

#### 第二批

- 在线检索器
- 分层判定状态机
- `LocalKernel.resolve_standard_evidences()`
- 调试脚本

交付结果：

- 能针对单条 `FormRow` 命中三级标题并完成分层判定。

#### 第三批

- `QwenRequester.judge_standard_context()`
- `QwenRequester.enrich_form_with_evidences()`
- `orchestrator.py` 标准阶段接入

交付结果：

- 标准补充阶段完成从“整本送模”到“受控分层证据送模”的切换。

### 17.9 完成定义

本方案落地完成的判断标准：

- 标准索引目录可独立长期保留，不依赖 `runtime/`。
- `--sync` 支持新增、修改、缺失补齐。
- 至少对 `standards/企业标准` 中的 3 份典型标准可以切出主要试验章节。
- 在线检索能稳定命中高温、盐雾、防水等代表性试验。
- 标准补充阶段默认只发送命中的章节证据，不再发送整份标准 PDF。
- 整个改造对外 API 不产生破坏性变化。
