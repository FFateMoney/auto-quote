# Auto Quote

结构化报价流程原型。当前版本已支持 Word、Excel、PDF 等文档预处理，并支持本地标准文件索引与标准证据补充。

## 启动

先安装前端依赖：

```bash
cd /my_storage/chen/auto-quote
npm install
```

然后直接执行一键启动脚本：

```bash
cd /my_storage/chen/auto-quote
./start.sh
```

脚本会读取 `config.yaml` 里的 `startup` 配置，同时启动前后端。
默认前端地址为 `http://127.0.0.1:5173`，默认后端地址为 `http://127.0.0.1:8000`。

## 目录

- `standards/企业标准`
- `standards/国家标准`
- `data/standard_index`
- `runtime/runs/<run_id>`
- `test/测试需求1.docx`

## 说明

- 配置文件为 `config.yaml`，已按当前本机环境准备好。
- 一键启动脚本为 `start.sh`，内部会按 `config.yaml > startup` 自动读取 conda 环境名、前后端 host/port 和是否自动打开浏览器。
- 标准库目录已切换到新仓库根目录下的 `standards/`。
- 标准索引目录为 `data/standard_index/`，索引文件以规范化后的 `standard_key` 命名。
- `standard_key` 规则：仅保留英文字符和数字，按原顺序拼接后转小写；中文、空格、符号和扩展名全部去掉。
- 当标准库新增或修改 PDF 后，可执行以下命令重建索引：

```bash
cd /my_storage/chen/auto-quote
/my_storage/chen/conda/envs/quote/bin/python -m packages.integrations.standard_indexer --rebuild
```

- 若想根据首页文本生成“待人工确认”的标准文件重命名映射，可执行：

```bash
cd /my_storage/chen/auto-quote
/my_storage/chen/conda/envs/quote/bin/python -m packages.integrations.standard_filename_renamer --generate
```

  生成结果位于 `data/standard_index/rename_candidates.txt`。

- 人工删除或修改映射文件中的行后，可执行一键重命名：

```bash
cd /my_storage/chen/auto-quote
/my_storage/chen/conda/envs/quote/bin/python -m packages.integrations.standard_filename_renamer --apply
```

- 若自动报价缺字段，前端会在同一张表上进入人工补录。
