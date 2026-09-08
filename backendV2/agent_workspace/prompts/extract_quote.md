# 报价表提取任务

你正在处理一次报价任务。Core 的初始指令会给出本次任务目录 `<run_dir>`，它相对于当前工作目录 `agent_workspace/`。请先阅读 `<run_dir>/quote_table.schema.json`，它定义一张独立报价表的外层格式。

1. 阅读 `<run_dir>/input/` 中的原始报价需求文件，自主使用命令、Python 和可用的文档查看能力理解文件内容。
2. 将报价拆为原子单位：一个实验类型的一个独立试验需求就是一份独立报价。文档中的 Group、项目组、样品组、测试计划或并行台架信息只提供样品数量、时长等上下文，不能作为合并多种实验类型的报价边界。
3. 调用 `quote-core query-test-projects --run-dir <run_dir>`。该命令会在 `<run_dir>/test_projects.json` 生成测试项目三元组目录。每项包含 `id`、`standard_type`、`test_item`、`max_specification` 和 `pricing_mode`。
4. 对每份独立报价，从目录中选择一个最匹配的测试项目三元组。不同三元组必须分别成表；同一三元组但试验条件、标准章节、样品数量或计价数量不同，也必须分别成表。先按目录中的标准类型和测试项目进行完全匹配；仅当报价文档中的试验名称无法完全匹配目录中的任一标准类型或测试项目时，才可对可能对应的项目调用 `quote-core query-test-project-aliases --run-dir <run_dir> --test-project-id <id>`，阅读生成的 `<run_dir>/aliases/test_project_<id>_aliases.json` 作为别名映射参考。别名匹配后仍填写对应的标准 `test_project_id`。仅当一份独立试验需求确实无法匹配任何三元组时，才将该报价的 `test_project_id` 设为 JSON `null`；不得把多个无法匹配的需求合并成一张表。
5. 对每个已选择三元组的报价，调用 `quote-core query-test-project-capability-fields --run-dir <run_dir> --test-project-id <id>`。该命令生成 `<run_dir>/schemas/test_project_<id>_schema.json`。文件是该报价的完整 `values` 模板，分为 `固定字段` 和 `专有字段` 两部分；保留所有字段，不得新增、删除或改名。
6. 每个独立报价使用一个目录和一张表：`<run_dir>/quotes/<quote_id>/quote_table.json`。表格包含 `schema_version`、`test_project_id` 和 `values`，不包含 `items` 列表。`quote_id` 只用于目录命名，应稳定且便于识别。将模板复制为 `values` 后填写：来源文件没有明确值时保持 JSON `null`。`raw_test_type` 填写在 `固定字段` 中，不能填写 JSON `null`。`pricing_mode` 和 `specification` 已由模板按所选三元组写入，不能修改；按 `pricing_mode` 填写 `pricing_quantity`：`时长`的计价数量单位固定为小时，填写总试验时长；来源以天、分钟或其他时间单位描述时，先换算为小时再填写。`批次`填写批次数量，`人日`填写人日数量。无法匹配三元组时，`固定字段` 填写 `raw_test_type`、`standard_code`、`standard_document_section`、`pricing_mode`、`specification`、`pricing_quantity`、`sample_count`、`length_mm`、`width_mm`、`height_mm`，其中 `pricing_mode` 和 `specification` 保持 `null`，`专有字段` 填写空对象 `{}`。
7. 对每张表调用 `quote-core validate-quote-table --run-dir <run_dir> --file quotes/<quote_id>/quote_table.json`，并阅读该报价目录内的 `validation_result.json`。
8. 所有报价表准备完成后，调用一次 `quote-core submit-batch --run-dir <run_dir>`，并阅读 `<run_dir>/submit_result.json`。
9. 当 `<run_dir>/submit_result.json` 的 `accepted` 为 `true` 时结束任务。若消息为“格式错误”，根据 `details` 修正对应报价表后，从校验步骤继续。

每张报价表的 `固定字段` 和 `专有字段` 必须填写动态模板中的全部字段，不能省略。来源文件没有明确值时填写 JSON `null`；有明确值时使用字段名称对应的单位。不要推测报价金额或未出现的试验要求。报价表不得包含动态模板之外的字段。默认每个源文件试验需求单独成表；即使选择同一测试项目三元组，只能在试验条件、标准章节、样品数量和计价数量完全一致时合并。任一项不同都必须保留为两张独立报价表。

文档中可能存在适用于多个或全部报价的共享内容。共享内容可以出现在文档的任意位置，例如说明区、备注区、标题旁、页首、页尾或独立段落，不能仅按其所在行列判断是否适用。先识别这些共享事实，再将其中能够映射到动态模板字段的值填写到每一张适用的报价表中。某个报价项目自身给出同一字段的更具体值或冲突值时，以该项目自身的值为准；没有项目级值时使用共享值。比如共享说明给出样品尺寸约 30cm × 25cm × 5cm，则相关报价表填写 `length_mm: 300`、`width_mm: 250`、`height_mm: 50`。尺寸优先使用明确的样品尺寸；未出现样品尺寸直接描述时，夹具、外包装等承载对象给出的长宽高或长宽尺寸可作为样品尺寸替代，缺失的维度填写 `null`。

## 知识补全

按以下优先级补全每份报价表的信息：

1. 完整阅读报价需求文档自身的内容。文档内的标准条款、测试描述、参数表、说明和附件页都可以作为该报价的知识来源。
2. 检查 `<run_dir>/input/` 中是否存在报价需求之外的知识文档。存在时必须阅读与报价项目相关的知识文档，并将其中的有效信息补入对应报价表。
3. 当已选定测试项目三元组、且 `standard_code` 已确定，但仍缺少需要依据标准才能确定的试验条件、时长、次数、循环或性能参数时，先调用 `quote-core query-history-quotation-cache --run-dir <run_dir> --standard-type <标准类型> --test-item <测试项目> --standard-code <标准号>`。命令会输出一个缓存文件路径；读取该文件中的 `items`。文件仅包含可复用的标准条件字段，可以补入对应报价表。报价需求文档及其输入附带知识文档与缓存值冲突时，以输入文件为准。不要自行判断缓存字段、分组规则或复用范围。
4. 仅当 `input/` 中没有独立知识文档，且报价需求自身与历史报价缓存的信息仍不足以完成报价时，才检索项目根目录的 `data/cleaned_markdown/`。信息不足是指缺少需要依据标准才能确定的关键试验条件、时长、次数、循环或性能参数；某个动态模板字段为 `null` 本身不代表信息不足。
   - 以 `standard_code` 和 `standard_document_section` 为主要线索，使用 `rg`、文件名检索或字符串拆分列出候选标准文档，再阅读候选内容确认。
   - 标准编号必须实质一致。版本、修订号或分册不同的标准不是同一文档，例如 `GJB 150.16A-2009` 与 `GJB 150.16B-2009` 不匹配；`GJB 150.16A-2009` 与 `GJB 150.16A-2009军用标准` 可以匹配。
5. 若已定位到所需标准文档，但 `data/cleaned_markdown/` 中的文字混乱或缺失关键内容，则从项目根目录的 `data/origin/` 中读取对应原始 PDF，继续补全该报价表。

知识资料不能用于推断样品的 `length_mm`、`width_mm` 或 `height_mm`。这些字段只能使用报价需求文档及其输入附带资料中的信息；仍无法确认时填写 `null`。

## PDF 页面识别

PDF 的文字提取只用于快速定位目录、章节和候选页面，不能视为 PDF 信息的唯一来源。PDF 中的曲线图、图片表格、扫描页和嵌入图片可能包含试验参数，例如频率范围、加速度、位移、温度曲线、持续时间或循环次数。

当已通过文字定位到与报价项目相关的 PDF 页面时，渲染该页面为图片并使用可用的视觉能力读取其中的图表和图片信息，再填写对应动态模板字段。若 PDF 没有可用文字层、文字提取结果为空或明显混乱，则直接将相关页面渲染为图片并使用视觉能力识别。只将图像中能够明确辨认的数值和条件写入报价表；无法明确辨认时填写 `null`。
