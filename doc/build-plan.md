# 构建与扩充计划

## 1. 文档目的

本文档用于描述 `/my_storage/chen/auto-quote` 当前已经落地的系统基线，以及后续扩充的优先级。

它不是“从零开始的新仓库设想”，而是：

- 当前真实实现的摘要
- 已完成能力与边界
- 接下来建议继续推进的任务列表

如与历史讨论稿冲突，以当前代码实现为准。

## 2. 当前系统目标

系统的核心对象仍然只有一张“结构化报价表”。

所有流程都围绕这张表做增量填写与状态推进：

- 文档抽取
- 试验类型匹配
- 设备筛选
- 标准补充
- 重新筛选设备
- 最终报价
- 人工补录后继续报价

前端只展示结构化表单及其阶段快照，不展示旧系统中的中间文本、候选 JSON、决策轨迹等调试型信息。

## 3. 当前技术基线

- 后端：FastAPI
- 前端：React + TypeScript + Vite
- 模型：`qwen3-omni-flash`
- 阶段状态持久化：`runtime/runs/<run_id>/run_state.json`
- 标准索引持久化：`data/standard_index/`
- 标准来源：仅本地标准库
- Web 请求模式：前端同步调用后端接口，后端在一次请求内完成整次 run

## 4. 当前整体流程

```text
上传文件
-> 文档预处理
-> 文档抽取
-> 试验类型匹配
-> 设备初筛
-> 标准补充
-> 设备复筛
-> 最终报价
```

### 4.1 当前阶段顺序

代码中的阶段顺序为：

1. `document_extracted`
2. `test_type_matched`
3. `equipment_selected`
4. `standard_enriched`
5. `final_quoted`

注意：

- `equipment_selected` 在运行中会被写入两次：
  - 第一次表示设备初筛
  - 第二次表示标准补充后的设备复筛
- `standard_enriched` 已经不再是“前置标准补充”，而是“设备筛选后、按缺失字段驱动的定向标准补充”

## 5. 当前目录结构

```text
/my_storage/chen/auto-quote
├── apps/
│   ├── api/                         # FastAPI 入口
│   └── web/                         # React 前端
├── packages/
│   ├── core/                        # 编排、报价、状态、数据模型
│   ├── integrations/                # Qwen、标准检索、适配器、配置
│   └── plugins/                     # 文档处理插件
├── standards/                       # 本地标准文件库
├── data/standard_index/             # 标准索引（持久化）
├── runtime/                         # run 运行态产物（允许删除）
├── prompts.json                     # 提示词
├── config.yaml                      # 配置
├── requirements.txt                 # Python 依赖
└── package.json                     # 前端依赖
```

## 6. 当前核心数据模型

### 6.1 FormRow

`FormRow` 是唯一业务基线。当前关键字段包括：

- 识别类：
  - `row_id`
  - `raw_test_type`
  - `canonical_test_type`
  - `standard_codes`
- 计价类：
  - `pricing_mode`
  - `pricing_quantity`
  - `repeat_count`
- 样品类：
  - `sample_length_mm`
  - `sample_width_mm`
  - `sample_height_mm`
  - `sample_weight_kg`
- 条件类：
  - `required_temp_min`
  - `required_temp_max`
  - `required_humidity_min`
  - `required_humidity_max`
  - `required_temp_change_rate`
  - `required_freq_min`
  - `required_freq_max`
  - `required_accel_min`
  - `required_accel_max`
  - `required_displacement_min`
  - `required_displacement_max`
  - `required_irradiance_min`
  - `required_irradiance_max`
  - `required_water_temp_min`
  - `required_water_temp_max`
  - `required_water_flow_min`
  - `required_water_flow_max`
- 文本类：
  - `source_text`
  - `conditions_text`
  - `sample_info_text`
- 状态与结果类：
  - `source_refs`
  - `missing_fields`
  - `blocking_reason`
  - `candidate_equipment_ids`
  - `selected_equipment_id`
  - `rejected_equipment`
  - `base_fee`
  - `unit_price`
  - `total_price`
  - `formula`
  - `standard_evidences`
  - `standard_match_notes`

### 6.2 当前报价公式

当前总价公式已经是：

```text
(基础费 + 单价 × 计价数量) × 重复次数
```

其中：

- `pricing_quantity` 表示单次执行的计价数量，例如 `5 小时`
- `repeat_count` 表示同一测试需要重复执行的次数/工件数，例如 `3 件`

若 `repeat_count` 为空，当前实现默认按 `1` 处理。

## 7. 当前已实现的文档处理能力

当前已接入插件：

- Word
- Excel
- PDF
- Image

当前实现特点：

- Excel 已支持“首行既可作为 header，也保留为原始数据行”
- PDF 支持文本提取与图片抽取
- 运行时上传文件不再复制到 `runtime/runs/<run_id>/uploads/`
- run 目录名已改为可读形式：
  - `第一个上传文件名_年月日时分秒`

## 8. 当前标准补充机制

### 8.1 总原则

标准补充已经从“前置整本送模”改成：

- 设备初筛后触发
- 只针对缺失字段触发
- 只发送命中的标准证据
- 不再回退整本 PDF

### 8.2 当前真实流程

1. `attach_standard_refs()`
   - 根据 `standard_codes` 找到本地标准文件
2. `resolve_standard_evidences()`
   - 命中一个最高分三级标题
   - 生成范围扩展链，例如：
     - `5.1.3`
     - `5.1.*`
     - `5.*`
3. 标准补表按轮次进行：
   - 所有待补字段共享同一条扩展链
   - 每轮只发送“当前范围新增进入的章节内容”
   - 本轮补出的字段立即从剩余待补字段中移除
   - 若仍有剩余字段，再进入下一轮范围
   - 最多扩展两次

### 8.3 当前增量发送规则

范围扩展不是整包重复发送，而是增量发送：

- `5.1.3 -> 5.1.*`
  - 第二轮不再重复发送 `5.1.3`
- `5.1.* -> 5.*`
  - 第三轮只发送新进入范围的 `5.2 / 5.3 / ...`

### 8.4 当前限制

- 标准补充只对 `STANDARD_FILLABLE_FIELDS` 生效
- 样品尺寸、样品重量等实物字段仍不应由标准推断
- 标准补充是“按字段定向补”，不是“补完整个项目的一切字段”

## 9. 当前前端展示原则

前端当前保留：

- 上传区
- 运行状态
- 阶段切换
- 结构化报价表
- 被筛除设备表
- 人工补录区

当前不展示：

- 文档原文调试区
- 清洗后文本
- 标准候选 JSON
- 决策轨迹原文
- 模型完整响应

## 10. 当前已完成的重要修正

以下设计与实现已经落地：

- 标准补充后移到设备初筛之后
- 标准检索模块独立化
- 本地标准索引持久化到 `data/standard_index/`
- 标准证据改为范围扩展与增量发送
- 前端长请求超时从 20 秒放宽到 10 分钟
- run 目录改为可读命名
- 运行时不再保存上传副本
- Excel 无表头首行不再被吞掉
- 顶层缺失字段与阻塞原因改为中文标签展示
- 温变速率缺失重复提示已修正
- 报价公式已支持 `repeat_count`

## 11. 当前仍存在的边界

以下内容仍然成立，属于当前系统边界：

- 后端仍是同步长请求模型
- 前端不会轮询后台任务状态
- 标准补充仍只依赖本地标准库
- 温变速率很多时候需要从标准曲线中推导，未必能直接抽取成唯一数值
- 标准补充仍然可能不足以覆盖样品类字段

## 12. 后续扩充优先级

### 12.1 P0：稳定性与准确性

- 为标准补充增加端到端回归样例
- 为典型标准建立字段覆盖测试
- 明确哪些字段允许标准补、哪些绝不允许
- 优化标准补充日志，记录每轮范围与每轮新补字段

### 12.2 P1：报价语义增强

- 区分“计价数量”和“重复次数”的更多示例抽取
- 支持“3 件样品共用一次试验”与“3 件样品分别执行 3 次”这类边界语义
- 视业务需要考虑是否拆分：
  - `repeat_count`
  - `sample_count`
  - `execution_count`

### 12.3 P1：标准补充增强

- 对温变速率增加推导规则
- 对表格型标准页增强解析
- 对扫描版 PDF 的 OCR 结果形成更稳定的检索资产
- 增加标准补充失败的可观测性

### 12.4 P2：运行模式改造

- 若后续 run 时间进一步变长，可把同步长请求改为异步任务
- 前端改成：
  - 创建 run
  - 返回 run_id
  - 轮询 `/api/runs/{run_id}`

### 12.5 P2：文档与运维

- 持续同步 `CLAUDE.md`
- 持续同步 `standard-pdf-retrieval-design.md`
- 为常见 run 问题建立排查清单

## 13. 测试建议

### 13.1 单元测试

- `FormRow` merge 行为
- `repeat_count` 报价计算
- 标准范围扩展链生成
- 增量 evidence 生成
- 设备缺失字段与中文标签映射

### 13.2 集成测试

- Excel 无表头单行抽取
- 设备初筛后触发标准补充
- `5.1.3 -> 5.1.* -> 5.*` 增量补表
- 标准补充后设备复筛
- 人工补录后继续报价

### 13.3 Web 验收

- 长请求不再因 20 秒超时报错
- 待补字段显示中文，不显示内部字段名
- 被筛除设备表中的缺失字段显示中文
- 重复次数正确出现在表中并参与报价

## 14. 当前结论

项目已经不再处于“从零搭架构”的阶段，而是已经形成了可运行主链路。

后续工作的重点不再是重写主流程，而是：

- 提高标准补充命中率
- 提高字段补全准确率
- 降低长请求风险
- 增强报价语义表达能力
- 保持文档与实现一致
