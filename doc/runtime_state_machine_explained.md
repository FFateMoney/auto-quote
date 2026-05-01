# 报价运行级状态机说明

这份文档只解释“运行级状态机”在实际执行时每一步做了什么，尽量不用抽象术语，方便直接讨论字段应该放在哪一步。

对应主流程代码：
- [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py)
- [backend/quote/stages.py](/my_storage/chen/auto-quote/backend/quote/stages.py)

## 1. 先看结论

当前一次自动报价运行，主流程是：

1. 接收上传文件，创建 `RunState`
2. `document_extracted`：把文件转成标准化文本/图片，再让大模型抽结构化报价表
3. `test_type_matched`：把抽到的试验名称映射到内部试验类型
4. `equipment_selected_initial`：按尺寸、温湿度、载荷等条件做设备初筛，并生成标准补充模板字段
5. `standard_enriched`：基于模板字段和标准证据，先做字段发现，再补系统支持字段，同时记录额外标准要求
6. `equipment_selected_enriched`：因为标准补充后，设备筛选条件可能变了，所以重新筛设备，并根据最终选中的设备计算 `repeat_count`
7. `final_quoted`：按价格规则计算最终报价

注意：
- 设备筛选现在拆成两个显式阶段：`equipment_selected_initial` 和 `equipment_selected_enriched`。
- `stage_status` 不是完整状态机，它更像“这一行现在是否能继续报价”的行级标记。
- 运行最终的总状态不是阶段名，而是 `running / waiting_manual_input / completed / failed`。

## 2. 当前有哪些“状态”

### 2.1 运行级阶段

定义在 [backend/quote/stages.py](/my_storage/chen/auto-quote/backend/quote/stages.py:1)：

- `document_extracted`
- `test_type_matched`
- `equipment_selected_initial`
- `standard_enriched`
- `equipment_selected_enriched`
- `final_quoted`

这些阶段会被写进 `RunState.current_stage`，并在 `RunState.form_stages` 中保存当时整张表的快照。

### 2.2 运行总状态

定义在 [backend/quote/models.py](/my_storage/chen/auto-quote/backend/quote/models.py:194)：

- `running`
- `waiting_manual_input`
- `completed`
- `failed`

它表示“这次运行整体现在是什么结果”，不是表示流程走到了哪一步。

举例：
- 流程已经走到 `final_quoted`，但如果还有缺字段，`overall_status` 仍然可能是 `waiting_manual_input`
- 流程中任一步抛异常，`overall_status` 会变成 `failed`

### 2.3 行级状态

行级字段是 `FormRow.stage_status`，定义在 [backend/quote/models.py](/my_storage/chen/auto-quote/backend/quote/models.py:118)。

当前代码里它主要在报价阶段使用，常见值只有：

- `quoted`
- `waiting_manual_input`

也就是说，它目前不是“文档抽取中/设备筛选中/标准补充中”这种完整状态机，只是最终报价时给每一行打结果标记。

## 3. 主流程详细说明

下面按真实执行顺序展开。

---

## 4. 创建运行

入口在 [backend/quote/http/routes.py](/my_storage/chen/auto-quote/backend/quote/http/routes.py:59) 的 `POST /api/runs`。

这一段会做的事情：

1. 接收上传文件
2. 生成 `run_id`
3. 把原文件保存到 `run_dir/uploaded/`
4. 组装 `UploadedDocument`
5. 调用 `QuoteOrchestrator.run(...)`

`QuoteOrchestrator.run(...)` 在真正开始处理前，会先创建一个初始 `RunState`，见 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:53)。

这时初始状态通常是：

- `overall_status = "running"`
- `current_stage = ""`
- `next_action = "系统正在处理文档"`

这一步还没有结构化报价表，只是把运行上下文建起来。

---

## 5. `document_extracted`：文件抽取

这是第一步真正的业务处理，代码在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:72) 到 [80](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:80)。

### 5.1 先做文档预处理

调用 `_preprocess(...)`，见 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:168)。

它会对每个上传文件：

1. 按扩展名选择插件，见 [backend/quote/plugins/registry.py](/my_storage/chen/auto-quote/backend/quote/plugins/registry.py:24)
2. 调用对应插件的 `preprocess(...)`，接口定义在 [backend/quote/plugins/base.py](/my_storage/chen/auto-quote/backend/quote/plugins/base.py:10)
3. 把原始文件转成统一的 `NormalizedDocument`

`NormalizedDocument` 里主要有三类信息，定义在 [backend/common/models.py](/my_storage/chen/auto-quote/backend/common/models.py:38)：

- `source_name` / `source_kind`：文件来源信息
- `text_blocks`：标准化后的正文块
- `assets`：文档里的图片，转成可传给多模态模型的 `data_url`

这一步的目标很简单：
- 不管用户传的是 Word、Excel、PDF 还是图片，后面都统一按同一种文档结构处理

### 5.2 再做首轮 LLM 抽取

预处理完成后，调用 `self.requester.extract_form(documents, ...)`，见 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:75)。

这一轮模型会收到：

- 文档清单
- 文档正文
- 图片输入
- 固定 JSON schema
- 字段规则

核心目标是：直接产出结构化报价表 `items`

对应实现见：
- [backend/quote/llm/requester.py](/my_storage/chen/auto-quote/backend/quote/llm/requester.py:195)
- [backend/quote/llm/prompts.json](/my_storage/chen/auto-quote/backend/quote/llm/prompts.json:2)

### 5.3 这一步会填哪些字段

这一阶段是“字段第一次出现”的关键阶段。

当前会在这里直接由模型抽出的字段包括：

- 试验名称：`raw_test_type`、`canonical_test_type`
- 标准号：`standard_codes`
- 计价信息：`pricing_mode`、`pricing_quantity`
- 件数信息：`sample_count`
- 样品信息：`sample_length_mm`、`sample_width_mm`、`sample_height_mm`、`sample_weight_kg`
- 条件范围：温度、湿度、振动、辐照、水温、水流量等
- 文本摘要：`source_text`、`conditions_text`、`sample_info_text`

也就是说：
- 样品长宽高目前是在这一步第一次填写
- `repeat_count` 在这一步不再提取，模型也完全看不到这个字段

### 5.4 这一步结束后系统保存什么

这一阶段完成后会调用 `_upsert(..., DOCUMENT_EXTRACTED, ...)`，见 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:80)。

保存结果包括：

- `RunState.current_stage = "document_extracted"`
- 在 `form_stages` 中保存一份“文件抽取”快照
- 表里已经有第一版 `FormRow[]`

### 5.5 这一步可能出现的问题

- 文件格式不支持，预处理直接失败
- 模型没抽出某些字段
- 模型字段格式不标准，但后处理会尽量做数值清洗

这里有一个重要现实：
- 这一阶段只负责“从文档里抽字段”，还不判断这些字段能不能真正用于后续报价

---

## 6. `test_type_matched`：试验类型匹配

代码在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:84) 和 [backend/quote/kernel.py](/my_storage/chen/auto-quote/backend/quote/kernel.py:21)。

### 6.1 这一步做什么

对每一行报价项：

1. 用 `canonical_test_type` 或 `raw_test_type` 去内部目录表里找试验类型别名
2. 找到后，回填系统内部标准名
3. 顺手补一部分基础元数据

会补的内容通常有：

- `canonical_test_type`
- `matched_test_type_id`
- `base_fee`
- `pricing_mode`

### 6.2 这一步的目标

把“大模型识别出来的自然语言项目名”接到“系统内部可报价的试验类型”上。

如果这一步没匹配上，后面会受影响：

- 设备没法按试验类型筛
- 价格规则也很可能找不到

### 6.3 这一步结束后保存什么

- `RunState.current_stage = "test_type_matched"`
- 保存“实验类型匹配”快照

### 6.4 这一步不会做什么

- 不会补长宽高
- 不会补重复次数
- 不会算价格
- 不会查标准正文

---

## 7. 第一次 `equipment_selected`：设备初筛

代码在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:89) 和 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:91)。

### 7.1 这一步做什么

系统会根据试验类型，从目录里拿到候选设备，然后逐台判断兼容性。

当前会检查的约束主要有：

- 样品长宽高是否超出设备长宽高
- 样品重量是否超过设备载荷
- 温度、湿度上下限是否满足
- 温变速率是否满足
- 振动、加速度、位移、辐照、水温、水流量等能力是否满足

### 7.2 这一步的输出

每行会得到：

- `candidate_equipment_ids`
- `candidate_equipment_profiles`
- `selected_equipment_id`
- `rejected_equipment`
- `missing_fields`

含义可以直白理解为：

- 哪些设备能用
- 哪些设备被淘汰了
- 被淘汰的原因是什么
- 如果某个字段缺失导致无法判断，也会记在 `missing_fields`

### 7.3 这一步怎么选“当前设备”

如果有多个兼容设备，系统会按功率和设备 ID 排序，优先取第一台作为当前选择设备，见 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:95) 到 [100](/my_storage/chen/auto-quote/backend/quote/quoter.py:100)。

这只是“当前自动选择结果”，不是人工最终确认页面上的业务承诺。

### 7.4 这一步的一个容易忽略的行为

如果样品长、宽、高为空，当前代码会“跳过尺寸比较”，见 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:210) 到 [220](/my_storage/chen/auto-quote/backend/quote/quoter.py:220)。

也就是说：

- 现在尺寸为空，并不会直接卡死设备筛选
- 系统会继续往下走

这是当前实现的真实行为，后续如果尺寸变成强依赖字段，这里就需要重看。

### 7.5 这一步结束后保存什么

- `RunState.current_stage = "equipment_selected"`
- 保存“设备筛选”快照

这时还没有最终价格，只是初步知道“哪些设备可能能做”。

---

## 8. `standard_enriched`：标准补充

代码入口在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:182)。

这一阶段只在“有标准号，且存在允许由标准补充的缺失字段”时才会真正工作。

### 8.1 先决定有没有必要补

系统会先找每一行里哪些缺失字段是“允许由标准补充”的，判断逻辑在 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:174)。

当前允许由标准补的主要是环境和能力条件，例如：

- 温度
- 湿度
- 温变速率
- 频率
- 加速度
- 位移
- 辐照
- 水温
- 水流量

不允许由标准补的字段包括：

- 样品长宽高
- 样品重量

所以这一步不会补样品尺寸。

### 8.2 如果需要补，会做三件事

#### 第一步：挂接标准文件引用

代码在 [backend/quote/kernel.py](/my_storage/chen/auto-quote/backend/quote/kernel.py:41)。

系统根据 `standard_codes` 直接向标准索引检索候选章节，并将命中的章节写入 `standard_evidences`。

#### 第二步：解析标准证据范围

代码在：
- [backend/quote/kernel.py](/my_storage/chen/auto-quote/backend/quote/kernel.py:54)
- [backend/quote/standard/resolver.py](/my_storage/chen/auto-quote/backend/quote/standard/resolver.py:44)

系统会：

1. 先检索最可能相关的三级标题片段
2. 以这个片段为起点组织证据
3. 必要时向上扩展到父章节范围
4. 最多扩展两级
5. 把这些范围整理成 `standard_evidences`

这里得到的不是最终字段，而是“后面给模型补表用的证据包”。

#### 第三步：逐轮调用模型补字段

代码在 [backend/quote/standard_enrich.py](/my_storage/chen/auto-quote/backend/quote/standard_enrich.py:22)。

这一步是“渐进补充”：

1. 第 1 轮先用当前最小证据范围
2. 如果目标字段还没补出来，再换下一轮范围
3. 每轮只允许补指定的目标字段
4. 每轮结束后，把新补出的字段合并回当前行
5. 全部补齐或范围耗尽后结束

### 8.3 这一阶段的目标

它不是重新做整张表，而是只想解决一句话：

“设备初筛后，还缺哪些标准里可能写着的条件字段？”

### 8.4 这一步结束后保存什么

- `RunState.current_stage = "standard_enriched"`
- 保存“标准补充”快照
- 每行可能新增 `standard_evidences`、`standard_match_notes`
- 部分缺失条件字段可能被补齐

---

## 9. 第二次 `equipment_selected`：标准补充后的再筛选与重复次数计算

代码在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:98)。

这一步和第一次设备筛选调用的是同一套逻辑，但业务意义不同：

- 第一次筛选时，很多条件可能还缺
- 标准补充后，温湿度、能力边界等字段可能更完整了
- 所以要重新跑一遍设备兼容判断

这一步的作用是：

- 用补全后的字段重新判断设备
- 更新候选设备、剔除原因、缺失字段
- 避免第一次筛选因为条件不全而留下不该留下的设备
- 基于最终选中的设备长宽高和样品长宽高计算 `repeat_count`

### 9.1 这一步里 `repeat_count` 怎么算

当前实现里，`repeat_count` 会在第二次 `equipment_selected` 之后由系统给出默认建议值，而不是由模型抽取。

计算规则是：

1. 使用最终选中的设备，即 `selected_equipment_id`
2. 设备单批容量 = `floor(设备容积 / 单件样品体积)`
3. 单件样品体积使用 `sample_length_mm * sample_width_mm * sample_height_mm`
4. 总件数使用 `sample_count`
5. 默认 `repeat_count = ceil(sample_count / 设备单批容量)`

补充说明：

- 如果用户人工修改过 `repeat_count`，系统会保留人工值，不覆盖
- 如果样品长宽高不完整，`repeat_count` 保持为空
- 如果总件数 `sample_count` 为空，`repeat_count` 也保持为空
- 如果最终选中设备容积未知，`repeat_count` 保持为空
- 如果设备单批容量小于 `1`，该默认建议值无法生成

注意：
- `RunState.current_stage` 仍然会写成 `equipment_selected`
- 但快照备注里会写“标准补充后重新筛选设备”

所以如果只看阶段名，看不出这是“第一次筛”还是“第二次筛”；要结合 `notes` 看。

---

## 10. `final_quoted`：最终报价

代码在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:103) 和 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:112)。

这一阶段才真正决定：

- 能不能出价
- 这一行要不要等待人工补录
- 总价是多少

### 10.1 这一阶段逐行会怎么判断

#### 情况 A：没有选中设备

如果 `selected_equipment_id` 为空：

- 这一行标成 `waiting_manual_input`
- 写入 `blocking_reason`
- 整体运行状态会变成 `waiting_manual_input`

常见原因：

- 所有候选设备都被筛掉了
- 根本没匹配到试验类型

#### 情况 B：没有 `pricing_quantity`

如果缺少计价数量：

- 这一行标成 `waiting_manual_input`
- `missing_fields` 里加上 `pricing_quantity`
- 本轮不计算价格

#### 情况 C：有设备，但价格规则找不到

如果设备和试验类型都确定了，但没有唯一价格规则：

- 这一行标成 `waiting_manual_input`
- 不会生成总价

#### 情况 D：条件齐全，可以报价

这时系统会取：

- `base_fee`
- `unit_price`
- `pricing_quantity`
- `repeat_count`

然后计算：

`total_price = (base_fee + pricing_quantity * unit_price) * repeat_count`

对应代码见 [backend/quote/quoter.py](/my_storage/chen/auto-quote/backend/quote/quoter.py:153) 到 [163](/my_storage/chen/auto-quote/backend/quote/quoter.py:163)。

### 10.2 这一步里 `repeat_count` 的真实行为

当前实现里，报价阶段不会重新计算 `repeat_count`。

它只会读取前一步已经算好的值：

- 如果有值，就参与总价计算
- 如果为空，就挂起人工补录，不再默认按 `1` 报价

这说明：

- `repeat_count` 当前来源不是报价阶段
- 报价阶段只是消费它，不生产它
- `repeat_count` 现在已经是报价必需字段

### 10.3 这一步结束后保存什么

- `RunState.current_stage = "final_quoted"`
- `state.final_form_items = rows`
- `state.overall_status = completed` 或 `waiting_manual_input`
- `state.next_action` 变成“查看最终报价表或下载产物”或“补齐表格中的缺失字段后继续报价”

---

## 11. 流程失败时会发生什么

如果主流程任一步抛出异常，见 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:111)：

- `overall_status = "failed"`
- 错误信息写进 `errors`
- `next_action = "检查错误信息后重新上传文档"`

这属于“系统失败”，不是“业务字段缺失”。

---

## 12. 人工补录后继续报价时，状态机会怎么走

入口在 [backend/quote/http/routes.py](/my_storage/chen/auto-quote/backend/quote/http/routes.py:95) 的 `POST /api/runs/{run_id}/resume`。

对应主逻辑在 [backend/quote/orchestrator.py](/my_storage/chen/auto-quote/backend/quote/orchestrator.py:120)。

### 12.1 先做什么

系统会把用户手工填的字段写回指定行，代码在 [backend/quote/form_ops.py](/my_storage/chen/auto-quote/backend/quote/form_ops.py:110)。

同时：

- 记录 `manual_overrides`
- 清空原先的 `blocking_reason`
- 清空原先的 `missing_fields`

### 12.2 然后重新走哪些阶段

人工补录后，不会只重算最后一步，而是会重新走一遍后半段：

1. `test_type_matched`
2. `equipment_selected`
3. `standard_enriched`
4. `equipment_selected`
5. `final_quoted`

这样做的原因是：

- 你补的字段可能改变试验类型匹配
- 可能改变设备筛选结果
- 也可能让标准补充目标发生变化

### 12.3 这条路径的意义

系统的设计不是“让人工直接改总价”，而是：

- 人工补关键业务字段
- 让系统按同一套规则重新跑

这样可追踪，也更一致。

---

## 13. 一张图看懂每一步产出什么

| 阶段 | 主要输入 | 主要动作 | 主要产出 |
| --- | --- | --- | --- |
| 创建运行 | 上传文件 | 保存文件、创建 `RunState` | 初始运行记录 |
| `document_extracted` | 原始文档 | 预处理 + LLM 抽表 | 第一版 `FormRow[]` |
| `test_type_matched` | 第一版表格 | 匹配内部试验类型 | `canonical_test_type`、`matched_test_type_id` 等 |
| `equipment_selected` | 试验类型 + 当前字段 | 设备兼容性筛选 | 候选设备、剔除原因、缺失字段 |
| `standard_enriched` | 标准号 + 缺失条件字段 | 检索标准并补字段 | 补全后的条件字段、标准证据 |
| `equipment_selected` 再筛 | 补全后的字段 | 重新筛设备 | 更新后的候选设备结果 |
| `final_quoted` | 设备 + 价格规则 + 计价字段 | 计算价格或挂起人工补录 | `total_price`、`formula`、最终状态 |

---

## 14. 当前实现里最值得记住的几个事实

1. 样品长宽高第一次出现于 `document_extracted`，不是设备筛选阶段。
2. `repeat_count` 不再在 `document_extracted` 阶段由模型抽出，而是在第二次 `equipment_selected` 之后由系统计算。
3. `standard_enriched` 只补“允许由标准补”的字段，不补样品尺寸。
4. `equipment_selected` 一次运行里会执行两次。
5. `final_quoted` 会消费 `repeat_count`，但当前不会重新推导它；如果它为空，会挂起人工补录。
6. 当前尺寸为空时，设备筛选会跳过尺寸比较，不会自动把流程卡住。

---

## 15. 如果后面要改字段归属，最常见的讨论方式

以后讨论“某个字段应该在哪一步产生”时，可以直接按这三个问题判断：

1. 这个字段来自用户文档，还是来自系统计算，还是来自标准库补充？
2. 这个字段是否依赖设备筛选结果？
3. 这个字段为空时，是允许继续流转，还是必须挂起人工补录？

只要把这三个问题说清楚，字段应该落在哪个阶段，通常就比较容易定下来。
