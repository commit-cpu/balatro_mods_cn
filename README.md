# Balatro Mods CN

Balatro Mods CN 是一个自托管的 Balatro 模组简体中文汉化工作台。它用于追踪模组仓库、本地化覆盖率、AI 翻译、人工审核、写回 `zh_CN.lua`，并把审核后的结果提交到 GitHub fork 分支。

项目当前重点不是“模组管理器”，而是围绕 Balatro 模组汉化建立一套可持续协作的流水线。

## 当前能力

- 从 `balatro-mod-index` 读取模组名称、GitHub 仓库、分类、星标和依赖信息。
- 无需完整 clone 仓库即可探测 GitHub localization 文件。
- 只下载被选中模组的 localization 源文件，注册成本地可翻译源。
- 使用 OpenAI-compatible LLM 翻译缺失/未完成条目。
- 翻译流程支持 RAG 引用、名称预翻译、Lua 校验、循环修复、断点复用和 review 导入。
- 管理员页面支持单独管理模组、队列排序、自动翻译间隔、人工审核、应用已通过翻译、提交到 fork。
- 提交 fork 后，列表中的 AI 仓库按钮会跳到对应 fork 分支页面。

## 文档入口

- 使用流程：[docs/user-guide.md](docs/user-guide.md)
- 开发指南：[docs/developer-guide.md](docs/developer-guide.md)
- 贡献说明：[CONTRIBUTING.md](CONTRIBUTING.md)
- Agent 读码入口：[AGENTS.md](AGENTS.md)
- 翻译流水线细节：[docs/current-translation-pipeline.md](docs/current-translation-pipeline.md)
- 翻译质量和上下文策略：[docs/translation-quality-context-strategy.md](docs/translation-quality-context-strategy.md)

## 翻译流程

典型流程如下：

1. 打开管理员页面。
2. 选择一个模组。
3. 点击 `探测 GitHub`，检查 upstream 仓库是否有 localization 文件，以及当前汉化覆盖率。
4. 点击 `验证/创建 Fork`，确认 bot 账号 fork 可用。
5. 点击 `启动翻译`。
6. 后端只下载该模组的 localization 文件，创建本地 `mod_sources`，然后启动翻译 job。
7. 翻译 loop 会读取源 Lua，按 entry 分组，准备 RAG 引用和名称表，调用 LLM，写入 preview artifact。
8. loop 会尝试安全写回可自动应用的条目，并把需要人工判断的内容导入 review 列表。
9. 在管理员页面审核、编辑、整组通过。
10. 点击 `应用已通过`，把审核后的结果写入本地 `zh_CN.lua`。
11. 点击 `提交到 Fork`，提交到 `bot/zh-cn/{mod_id}` 分支。

翻译中刷新页面不会中断后端任务。任务状态和事件保存在 SQLite 的 `jobs` / `job_events` 中；翻译 artifact 位于 `data/artifacts/`。

## 运行环境

推荐环境：

- Python 3.12
- Docker / Docker Compose
- Node.js，仅用于检查前端 JS 语法
- `uv`，推荐用于 Python 环境管理
- Ollama 或其他 embedding 服务
- OpenAI-compatible LLM API
- GitHub token，用于 probe/fork/publish

## 快速启动

```bash
uv venv --python 3.12
uv sync --extra dev
cp .env.example .env
mkdir -p data/repos
git clone https://github.com/PIPIKAI/balatro-mod-index.git data/repos/balatro-mod-index
docker compose up -d
.venv/bin/python -m app.cli.main migrate
```

系统默认读取 `data/repos/balatro-mod-index/mods/all.json` 作为公开模组索引。这个文件来自 [PIPIKAI/balatro-mod-index](https://github.com/PIPIKAI/balatro-mod-index/blob/main/mods/all.json)。

启动 API：

```bash
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

常用页面：

- 公开列表：`http://127.0.0.1:8000/mods`
- 本地开发管理员页面：`http://127.0.0.1:8000/admin`
- 生产管理员页面：`http://127.0.0.1:8000/${ADMIN_PATH_SUFFIX}`

## 环境变量

复制 `.env.example` 后至少配置这些值：

```dotenv
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
LLM_CONCURRENCY=1

GITHUB_TOKEN=replace_me

QDRANT_API_KEY=replace_me
QDRANT_READ_ONLY_API_KEY=replace_me
```

Git/GitHub 访问代理：

```dotenv
GIT_HTTP_PROXY=http://127.0.0.1:7890
GIT_HTTPS_PROXY=http://127.0.0.1:7890
GIT_NO_PROXY=127.0.0.1,localhost
```

管理员生产保护：

```dotenv
ADMIN_PATH_SUFFIX=cnops-balatro-aadmin
ADMIN_SECRET_KEY=replace_with_long_random_secret
```

当 `ADMIN_SECRET_KEY` 为空时，项目处于本地开发模式，`/admin` 可直接打开。

当 `ADMIN_SECRET_KEY` 非空时：

- `/admin` 不注册，访问应返回 404；
- 管理员入口是 `/${ADMIN_PATH_SUFFIX}`；
- 未验证时会显示 `sk` 输入页；
- 验证通过后后端写入 HttpOnly cookie；
- workflow / review / queue / publish 等管理员 API 都需要该 cookie。

## Qdrant 和知识库

启动 Qdrant：

```bash
docker compose up -d
```

确认 Qdrant 可用：

```bash
source .env
curl -H "api-key: ${QDRANT_API_KEY}" http://127.0.0.1:6333/collections
```

确认 Ollama embedding 可用：

```bash
curl http://127.0.0.1:11434/api/embed \
  -d '{"model":"qwen3-embedding:8b","input":"test"}'
```

导入已有人工翻译作为 translation memory：

```bash
.venv/bin/python -m app.cli.main import-local-tm \
  --repo data/repos/Balatro__Origin \
  --mod-id balatro_origin \
  --source localization/en-us.lua \
  --target localization/zh_CN.lua
```

同步向量：

```bash
.venv/bin/python -m app.cli.main sync-vectors --limit 100
```

## 管理员页面

管理员页面主要区域：

- 模组选择：可搜索模组名称、仓库、本地 mod id。
- 管理视图：待翻译、队列、翻译中、待审核、已应用、已提交 Fork。
- 队列控制：加入队列、立即启动、上移、下移、重试、移除。
- 自动翻译设置：是否自动翻译、间隔小时。
- Review 列表：按 entry 分组审核 AI 翻译建议。
- Workflow 按钮：探测 GitHub、验证/创建 Fork、启动翻译、应用已通过、提交到 Fork。

自动翻译只会从队列里取下一个模组，并且同一时间不会启动多个翻译 job。

## 状态说明

公开列表里的状态分开表达：

- `当前汉化状态`：upstream/original 仓库中的 localization 覆盖率。
- `AI 翻译状态`：本系统对该模组的翻译、审核、fork 提交状态。
- `流程`：本系统建议的下一步操作。

因此，一个模组可能 upstream 仍是部分汉化，但 AI 状态已经是“已提交 Fork”。这表示本系统已经把结果提交到了 fork，还不代表 upstream 已经 merge。

## CLI 翻译预览

管理员页面使用的是 API workflow。调试单个仓库时，也可以直接跑 CLI preview：

```bash
bash -lc 'set -a; source .env; set +a; .venv/bin/python -m app.cli.main translate-entry-preview-mod \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --limit 20 \
  --top-k 5 \
  --max-width 25 \
  --concurrency 1 \
  --output data/artifacts/fortlatro_entry_translate_preview.jsonl'
```

应用 preview：

```bash
.venv/bin/python -m app.cli.main apply-entry-preview \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --input data/artifacts/fortlatro_entry_translate_preview.jsonl \
  --output localization/zh_CN.lua
```

如果需要允许 table-level 写回：

```bash
.venv/bin/python -m app.cli.main apply-entry-preview \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --input data/artifacts/fortlatro_entry_translate_preview.jsonl \
  --output localization/zh_CN.lua \
  --table-level
```

## 代码结构

- `app/api/`：FastAPI app、管理员 API、GitHub workflow、翻译 queue。
- `app/api/static/`：前端静态页面。
- `app/cli/`：CLI 和核心翻译 loop。
- `app/db/`：SQLite 连接和 migration runner。
- `app/github/`：GitHub probe、fork、publish、PR 相关逻辑。
- `app/lua/`：Lua 解析、提取、patch、校验。
- `app/llm/`：LLM client 和翻译/review prompt。
- `app/rag/`：translation memory、Qdrant、检索、术语检查。
- `migrations/`：SQLite schema migration。
- `tests/`：pytest 测试。

## 测试和检查

常用检查：

```bash
.venv/bin/python -m pytest -q
node --check app/api/static/app.js
git diff --check
```

开发时建议先跑 targeted tests：

```bash
.venv/bin/python -m pytest tests/test_translation_queue.py -q
.venv/bin/python -m pytest tests/test_api.py::test_admin_route_requires_secret_when_enabled -q
.venv/bin/python -m pytest tests/test_publish_workflow.py -q
```

某些完整 FastAPI `TestClient` 组合在当前环境中可能较慢。开发时优先跑 repository 级或单测级 targeted tests，提交前再跑完整测试。

## 发布前注意

- 不要提交 `.env`、真实 token、本地数据库、`data/repos/`、`data/artifacts/`。
- 生产环境必须设置 `ADMIN_SECRET_KEY`。
- GitHub token 需要具备 fork/contents 写入能力。
- 如果使用代理，确认 GitHub API 和 git clone/fetch 都能走通。
- 如果要长期运行自动翻译，建议从小队列开始，确认 LLM、Ollama、Qdrant、GitHub token 都稳定后再扩大规模。
