# 试验类型能力 Schema

每个 JSON 文件对应 `public.test_types` 中一个试验类型，并定义该类型的一张完整报价表。Agent 选择试验类型后，必须填写对应 schema 的全部字段；来源文件没有明确值时填写 `null`。`raw_test_type` 保留源文件原文，标准试验类型由报价表外层的 `test_type_id` 表示。`null.json` 用于无法确定试验类型的报价，包含通用报价字段、尺寸和最大载荷字段。

所有 schema 都包含以下字段：

- `length_mm`
- `width_mm`
- `height_mm`
- `max_load_kg`

每个 schema 还包含试验类型原文、标准号、标准文档章节、计价方式、计价数量和样品数量。温度、湿度、温变速率、频率、加速度、位移、辐照度和水流量只在对应试验类型的文件中出现。字段名与 `public.equipment` 的固定能力列或 `capabilities` JSON 键保持一致，供后续设备适配逻辑直接使用。

客户信息等未进入当前报价表的字段不在本目录定义。
