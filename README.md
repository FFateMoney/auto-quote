# Auto Quote

Auto Quote 是一个面向试验报价场景的自动化报价系统。它负责把客户提供的 Word、Excel、PDF、图片等需求文档转成结构化报价表，再结合本地标准库、设备能力和价格数据，完成试验类型匹配、设备筛选、标准证据补充和最终报价。

整体流程如下：

```text
上传文件 -> 文档预处理 -> 数据提取 -> 类型匹配 -> 设备初筛 -> 标准补充 -> 设备复筛 -> 最终报价
```

## 功能介绍

- 支持多种输入格式：Word、Excel、PDF、图片。
- 支持文档预处理与结构化字段提取，生成统一的报价表单行。
- 用户上传 PDF 当前按页转为图片送模；本地标准 PDF 仍走独立索引与检索链路。
- 支持试验类型匹配，将原始试验名称映射到库内规范类型。
- 支持设备初筛与复筛，按尺寸、温度、湿度、负载、温变速率等条件筛选候选设备。
- 支持本地标准库接入，对标准 PDF 建立索引并检索相关章节证据。
- 支持用标准证据回填缺失参数，减少人工补录。
- 支持报价计算，当前按基础费、单价、计价数量和重复次数计算总价。
- 提供 FastAPI 后端和 React 前端，支持上传、查看、编辑和继续处理报价任务。

## 仓库说明

这个仓库是代码仓库，不包含以下业务数据或私有资源：

- 标准 PDF 文件本体。
- `data/standard_index/` 下的标准索引产物。
- PostgreSQL 中的业务基础数据。
- 可用的模型密钥、数据库账号密码等本地配置。
- 外部 AIWord 服务脚本及其运行环境。

但仓库已经集成好了这些能力：

- 本地标准文件库接入。
- 标准 PDF 索引构建。
- 标准章节检索与范围扩展。
- 标准文件名规范化与候选重命名辅助。
- 基于数据库目录数据的自动匹配、设备筛选和报价流程。

也就是说，这个仓库默认不附带标准文件和数据库内容，但代码已经支持这些能力。把所需目录、文件和数据库准备好后，就可以直接运行。

## 准备运行环境

### 1. 安装依赖

前端依赖：

```bash
cd /my_storage/chen/auto-quote
npm install
```

后端依赖建议安装到项目使用的 Python 或 conda 环境中：

```bash
cd /my_storage/chen/auto-quote
pip install -r requirements.txt
```

### 2. 创建本地配置文件

以 `config.yaml.example` 为模板创建 `config.yaml`，至少补齐下面几类配置：

- `startup`: 前后端地址、端口、conda 环境名。
- `integrations`: 标准目录、标准索引目录、提示词路径、AIWord 脚本路径。
- `qwen`: 模型 API Key、模型名、Base URL。
- `database`: PostgreSQL 连接信息。

推荐格式如下：

```yaml
runtime:
  run_dir: "runtime/runs"

startup:
  conda_env: "quote"
  backend_host: "127.0.0.1"
  backend_port: 8000
  frontend_host: "127.0.0.1"
  frontend_port: 5173
  auto_open_browser: false

integrations:
  aiword_script_path: "/path/to/ai_edit.py"
  standards_dir: "standards"
  standard_index_dir: "data/standard_index"
  standard_index_enable: true
  standard_index_debug: true
  standard_retrieval_top_k: 5
  standard_retrieval_expand_neighbors: true
  prompts_path: "prompts.json"

qwen:
  api_key: ""
  model: "qwen3-omni-flash"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

database:
  dbname: "auto_quote"
  user: "postgres"
  password: ""
  host: "127.0.0.1"
  port: 5432
```

### 3. 准备标准文件目录

如果你要启用“本地标准检索与标准证据补充”能力，需要在仓库根目录准备标准文件目录：

```text
standards/
├── 企业标准/
└── 国家标准/
```

把标准 PDF 文件放到对应目录下即可。当前索引器会扫描 `standards/` 下的 PDF 文件并建立索引。

### 4. 准备标准索引目录

项目会把标准索引持久化到：

```text
data/standard_index/
```

这里要特别说明：`data/standard_index/` 不是用户手工补充的业务资料目录，而是代码运行后生成的索引产物目录。

你不需要手工往里面放文件。准备好 `standards/` 下的标准 PDF 后，执行索引命令，程序会在这里生成清洗结果、分块结果、向量索引和调试文件。

当标准文件准备完成后，可执行：

```bash
cd /my_storage/chen/auto-quote
python -m packages.integrations.standard_indexer --rebuild
```

如果只是增量同步新增或修改的 PDF，可执行：

```bash
cd /my_storage/chen/auto-quote
python -m packages.integrations.standard_indexer --sync
```

### 5. 准备 PostgreSQL 数据库

项目运行依赖 PostgreSQL，但仓库不包含建库结果和业务基础数据。你至少需要准备一个可连接的数据库，并填好 `config.yaml` 中的 `database` 配置。

从当前代码看，报价流程会读取这些表：

- `public.test_types`
- `public.equipment`
- `public.test_type_equipment`
- `public.equipment_pricing`

也就是说，除了创建数据库本身，还需要准备上述表结构和基础数据，否则类型匹配、设备筛选和报价都无法正常完成。

### 6. 可选：准备 AIWord 外部脚本

如果你要处理 Word 文档，还需要让 `config.yaml` 中的 `integrations.aiword_script_path` 指向可用脚本。这个外部依赖不在本仓库内。

## 启动方式

完成依赖安装、配置文件、标准目录和数据库准备后，可以直接执行：

```bash
cd /my_storage/chen/auto-quote
./start.sh
```

脚本会读取 `config.yaml` 中的 `startup` 配置，并同时启动：

- FastAPI 后端
- React 前端

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 常用命令

重建标准索引：

```bash
python -m packages.integrations.standard_indexer --rebuild
```

增量同步标准索引：

```bash
python -m packages.integrations.standard_indexer --sync
```

生成标准文件重命名候选：

```bash
python -m packages.integrations.standard_filename_renamer --generate
```

应用标准文件重命名映射：

```bash
python -m packages.integrations.standard_filename_renamer --apply
```

## 目录概览

```text
apps/                    前后端应用
packages/core/           核心编排、匹配、报价逻辑
packages/integrations/   数据库、模型、标准检索、索引等集成
packages/plugins/        Word/Excel/PDF/Image 文档处理插件
standards/               本地标准文件目录
data/standard_index/     标准索引持久化目录
runtime/runs/            运行时产物目录
```

## 适用说明

如果你只是想跑通仓库代码，除了安装依赖，还必须至少准备这几项：

- `config.yaml`
- `standards/` 下的标准 PDF
- PostgreSQL 数据库与基础业务表数据

其中 `data/standard_index/` 会在你执行标准索引构建后自动生成，不需要手工准备内容。缺少其余关键项时，系统都可能只能部分启动，无法完成完整报价流程。
