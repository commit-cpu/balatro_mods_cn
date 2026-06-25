# Balatro 模组中文本地化自动化平台
## 自建服务器版 MVP：Python + SQLite + Qdrant + 本地 GPU RAG

> 版本：Self-hosted MVP v1.1
> 更新：2026-06-25
> 定位：单服务器、自建向量数据库、AI 主导翻译与反馈闭环。  
> 本文替代此前“SQLite BLOB + NumPy 检索”的本地版方案。

> 当前代码进度、entry 级翻译预览流程、JSONL 契约、patchability 规则和下一步计划见
> [`docs/current-translation-pipeline.md`](current-translation-pipeline.md)。

---

# 0. 结论先行

你的本地方案应当是：

```text
Python / FastAPI      = 业务后端、任务编排、Git 自动化、翻译服务
SQLite                = 业务事实库：模组、任务、翻译版本、术语、反馈、审计日志
Qdrant                = 自建向量数据库：翻译记忆 embedding、向量检索、过滤检索
NVIDIA GPU            = 本地 embedding 与 reranker 推理
DeepSeek API          = 默认翻译与语言评审模型，可替换
Git / GitHub API      = 同步模组、维护 Fork、创建或更新 PR
```

**SQLite 不再保存 embedding，也不承担向量检索。**  
每一条允许进入正式 RAG 的翻译记忆，都由 Qdrant 保存为一个向量点。

推荐核心技术栈：

```text
Ubuntu Server
Docker Compose
Qdrant
Python 3.12 + uv
FastAPI
SQLite
qdrant-client
sentence-transformers + BAAI/bge-m3
FlagEmbedding + BAAI/bge-reranker-v2-m3
APScheduler
httpx
GitPython / Git CLI
LuaJIT
```

---

# 1. MVP 目标

## 1.1 用户最终看到的流程

```text
上游 GitHub 模组更新
→ 本机 scheduler 发现新 commit
→ 本机 worker 拉取仓库
→ 解析英文 Lua 本地化文件
→ 识别新增 / 修改的翻译单元
→ 从 Qdrant 检索高质量中英翻译记忆
→ 本地 GPU reranker 重排参考案例
→ LLM 翻译
→ 程序校验 Token / Lua / 文件差异
→ AI 独立评审，必要时自动重译
→ 更新自己的 Fork 与 zh_CN.lua
→ 按策略创建或更新上游 PR
→ 用户在反馈页指出某条翻译问题
→ AI 自动判断反馈
→ 有效反馈自动修正当前模组
→ 高置信度反馈经门槛后进入 Qdrant 翻译记忆库
```

## 1.2 人工参与边界

人工不参与日常校对。

人工只做：

```text
1. 收集初始的高质量人工中英翻译素材。
2. 在前端提交对具体译文的反馈。
3. 可选：维护少量全局术语。
```

日常决策由系统完成：

```text
是否翻译
是否重译
是否发布
是否采纳反馈
是否将反馈晋升为正式 RAG 记忆
```

## 1.3 容错边界

可容忍：

```text
个别表达不够自然
个别句子风格略有差异
某些描述不是人工精翻水平
```

绝不容忍：

```text
Lua 无法编译
变量 #1#、#2# 被删、改名、改序
样式 Token 如 {C:mult}、{} 被破坏
非文本 Lua 内容被修改
译文写错 key
重复提交、重复发 PR
```

因此：

```text
LLM 负责语言。
Python 负责结构安全。
Qdrant 负责语义检索。
SQLite 负责全部业务事实与审计。
```

---

# 2. 为什么选 Qdrant

## 2.1 选择

默认向量数据库：

```text
Qdrant，单节点 Docker Compose 部署。
```

不建议 MVP 同时上：

```text
Milvus
Weaviate
Elasticsearch
PostgreSQL + pgvector
Redis Vector
多个向量数据库并存
```

Qdrant 适合此项目的原因：

```text
Docker 单容器启动简单。
Python Client 成熟。
支持向量相似度检索。
支持 payload filter。
支持 HNSW 索引。
支持 collection snapshot。
后续可扩展为 dense / sparse / hybrid 检索。
```

## 2.2 Qdrant 与 SQLite 的职责划分

| 数据 | SQLite | Qdrant |
|---|---:|---:|
| 模组配置 | 是 | 否 |
| Git commit / 分支 / PR 状态 | 是 | 否 |
| 任务队列和重试状态 | 是 | 否 |
| 原始英文 / 中文译文 | 是 | 可选最小副本 |
| 翻译版本历史 | 是 | 否 |
| 用户反馈 | 是 | 否 |
| 术语库 | 是 | 否 |
| 高质量 TM 的 embedding | 否 | 是 |
| Qdrant point payload | 否 | 是 |
| 相似语义检索 | 否 | 是 |
| HNSW / ANN 索引 | 否 | 是 |

原则：

```text
SQLite 是唯一业务事实源。
Qdrant 是可重建的检索索引和向量服务。
```

当 Qdrant 损坏时：

```text
从 SQLite 的正式 tm_entries 重新生成 embedding 并回灌 Qdrant。
```

---

# 3. 单服务器架构

```text
                           ┌─────────────────────────────┐
                           │       GitHub 上游仓库         │
                           └──────────────┬──────────────┘
                                          │
┌─────────────────────────────────────────▼────────────────────────────────────┐
│                               自建 Linux 服务器                               │
│                                                                                │
│  ┌─────────────────────┐      ┌────────────────────────────────────────────┐ │
│  │ FastAPI             │      │ SQLite: data/balatro_cn.db                 │ │
│  │ - 管理 API          │◀────▶│ - mods / jobs / TM metadata / feedback     │ │
│  │ - 反馈 API          │      │ - translations / glossary / audit          │ │
│  └─────────┬───────────┘      └────────────────────────────────────────────┘ │
│            │                                                                   │
│            ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │ Python Worker                                                            │ │
│  │ - Git clone / fetch                                                      │ │
│  │ - Lua 解析、Token 保护、写回、Lua 编译校验                                │ │
│  │ - RAG 检索、LLM 翻译、AI 评审、反馈评估                                  │ │
│  │ - Qdrant vector outbox 同步                                               │ │
│  └───────────────┬────────────────────────────┬─────────────────────────────┘ │
│                  │                            │                               │
│                  ▼                            ▼                               │
│      ┌──────────────────────┐     ┌────────────────────────────────────────┐ │
│      │ NVIDIA GPU           │     │ Qdrant Docker Container                │ │
│      │ - BGE-M3 embedding   │────▶│ - tm_bge_m3_v1 collection              │ │
│      │ - reranker-v2-m3     │     │ - HNSW + payload filters               │ │
│      └──────────────────────┘     └────────────────────────────────────────┘ │
│                                                                                │
│  ┌─────────────────────┐      ┌────────────────────────────────────────────┐ │
│  │ APScheduler         │      │ Git worktree / local repos                 │ │
│  │ - 上游轮询          │────▶│ - upstream checkout / fork branch          │ │
│  │ - 备份 / 对账       │      └────────────────────────────────────────────┘ │
│  └─────────────────────┘                                                       │
└───────────────────────────────────────────────────────────────────────────────┘
```

## 3.1 GPU 的职责

GPU 用于：

```text
生成 embedding
生成 reranker 分数
可选：后续部署本地翻译模型
```

Qdrant 本身不依赖 GPU；它负责服务端向量存储、索引、搜索与过滤。

---

# 4. 项目目录

```text
balatro-cn-selfhosted/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── uv.lock
├── README.md
│
├── app/
│   ├── config.py
│   ├── scheduler.py
│   ├── worker.py
│   │
│   ├── api/
│   │   ├── main.py
│   │   ├── routes_mods.py
│   │   ├── routes_feedback.py
│   │   └── schemas.py
│   │
│   ├── db/
│   │   ├── connection.py
│   │   ├── migrate.py
│   │   ├── repositories.py
│   │   └── outbox.py
│   │
│   ├── jobs/
│   │   ├── dispatcher.py
│   │   ├── handlers.py
│   │   └── types.py
│   │
│   ├── rag/
│   │   ├── normalize.py
│   │   ├── embeddings.py
│   │   ├── qdrant_store.py
│   │   ├── lexical_search.py
│   │   ├── retriever.py
│   │   ├── reranker.py
│   │   └── quality_gate.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   ├── translator.py
│   │   ├── reviewer.py
│   │   ├── feedback_judge.py
│   │   └── prompts.py
│   │
│   ├── lua/
│   │   ├── lexer.py
│   │   ├── extractor.py
│   │   ├── tokens.py
│   │   ├── patcher.py
│   │   └── validator.py
│   │
│   ├── github/
│   │   ├── client.py
│   │   ├── repository_sync.py
│   │   └── pull_requests.py
│   │
│   └── cli/
│       ├── main.py
│       ├── import_tm.py
│       ├── qdrant_reindex.py
│       ├── sync_mod.py
│       └── evaluate.py
│
├── migrations/
│   ├── 001_init.sql
│   ├── 002_fts.sql
│   ├── 003_vector_outbox.sql
│   └── 004_indexes.sql
│
├── seed/
│   ├── glossary/
│   ├── translation_memory/
│   ├── mod_configs/
│   └── eval_cases/
│
├── data/
│   ├── balatro_cn.db
│   ├── repos/
│   ├── artifacts/
│   ├── backups/
│   └── qdrant/
│       ├── storage/
│       └── snapshots/
│
└── tests/
    ├── fixtures/
    ├── test_lua_tokens.py
    ├── test_lua_patcher.py
    ├── test_tm_import.py
    ├── test_qdrant_sync.py
    ├── test_retrieval.py
    └── test_pipeline.py
```

---

# 5. 服务器与基础环境

## 5.1 建议运行环境

```text
系统：Ubuntu Server LTS
Python：3.12
GPU：NVIDIA + 已正确安装驱动
Docker Engine + Docker Compose Plugin
Git
LuaJIT
```

MVP 不要一开始拆成多个物理服务器。

建议先部署为：

```text
一台服务器
一个 Qdrant 容器
一个 SQLite 文件
一个 Python API 进程
一个 Python worker 进程
一个 Python scheduler 进程
```

## 5.2 系统依赖

```bash
sudo apt-get update
sudo apt-get install -y \
  git \
  git-lfs \
  sqlite3 \
  libsqlite3-dev \
  luajit \
  build-essential \
  pkg-config \
  docker.io \
  docker-compose-plugin
```

检查：

```bash
git --version
sqlite3 --version
luajit -v
docker --version
docker compose version
nvidia-smi
```

`nvidia-smi` 必须正常显示 GPU，才能继续配置本地 embedding / reranker。

---

# 6. Qdrant 自建部署

## 6.1 安全原则

Qdrant 自建实例默认不应直接暴露到公网。

MVP 推荐：

```text
Qdrant REST / gRPC 仅绑定 127.0.0.1。
FastAPI 与 worker 从本机访问 Qdrant。
外部浏览器不直接访问 Qdrant Dashboard。
如果需要远程运维，通过 SSH Tunnel 访问。
```

必须启用：

```text
Qdrant API key
Docker persistent volume
定期 snapshot
```

## 6.2 `.env` 中的 Qdrant 密钥

```dotenv
QDRANT_API_KEY=请生成一个足够长的随机值
QDRANT_READ_ONLY_API_KEY=请生成另一个只读随机值
```

生成：

```bash
openssl rand -base64 48
```

## 6.3 `docker-compose.yml`

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: balatro-cn-qdrant
    restart: unless-stopped

    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"

    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
      QDRANT__SERVICE__READ_ONLY_API_KEY: ${QDRANT_READ_ONLY_API_KEY}
      QDRANT__LOG_LEVEL: INFO
      QDRANT__STORAGE__SNAPSHOTS_PATH: /qdrant/snapshots

    volumes:
      - ./data/qdrant/storage:/qdrant/storage
      - ./data/qdrant/snapshots:/qdrant/snapshots
```

启动：

```bash
docker compose up -d
docker compose ps
docker compose logs -f qdrant
```

注意：

```text
开发阶段可以使用 latest。
准备长期运行时，应把镜像 tag 固定到你已经测试过的版本。
升级 Qdrant 前先做 snapshot。
```

## 6.4 Qdrant 健康检查

```bash
curl \
  -H "api-key: ${QDRANT_API_KEY}" \
  http://127.0.0.1:6333/collections
```

没有 API key 时，应该被拒绝。

## 6.5 Python 连接

```python
from qdrant_client import QdrantClient

client = QdrantClient(
    url="http://127.0.0.1:6333",
    api_key=settings.qdrant_api_key,
    timeout=30,
)
```

---

# 7. Python 初始化

## 7.1 使用 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

mkdir balatro-cn-selfhosted
cd balatro-cn-selfhosted

uv init --python 3.12
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
```

## 7.2 PyTorch CUDA

PyTorch 的 GPU 安装命令取决于当前驱动、CUDA wheel 与系统环境。

安装步骤：

```text
1. 在 PyTorch 官方安装页面选择 Linux / Pip / Python / CUDA。
2. 复制页面当前生成的命令。
3. 在项目虚拟环境执行。
4. 立即运行 CUDA 检查。
```

检查脚本：

```bash
python - <<'PY'
import torch

print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda version:", torch.version.cuda)
print("gpu:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)

assert torch.cuda.is_available(), "CUDA 不可用，请检查 NVIDIA 驱动与 PyTorch CUDA 安装"
PY
```

## 7.3 Python 依赖

```bash
uv add \
  fastapi \
  "uvicorn[standard]" \
  pydantic \
  pydantic-settings \
  httpx \
  apscheduler \
  typer \
  rich \
  tenacity \
  python-dotenv \
  orjson \
  qdrant-client \
  sentence-transformers \
  FlagEmbedding \
  transformers \
  accelerate \
  huggingface-hub \
  gitpython \
  tree-sitter \
  tree-sitter-lua

uv add --dev \
  pytest \
  pytest-xdist \
  ruff \
  mypy
```

## 7.4 `.env.example`

```dotenv
APP_ENV=development
DATA_DIR=./data
DATABASE_PATH=./data/balatro_cn.db

API_HOST=127.0.0.1
API_PORT=8000

# Qdrant
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=replace_me
QDRANT_COLLECTION=tm_bge_m3_v1

# 本地 GPU 模型
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cuda
EMBEDDING_BATCH_SIZE=32
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_DEVICE=cuda
RERANK_USE_FP16=true

# 检索
RAG_DENSE_TOP_K=30
RAG_FTS_TOP_K=20
RAG_RERANK_TOP_K=16
RAG_REFERENCE_LIMIT=4

# LLM：默认 DeepSeek，也可换为任意 OpenAI-compatible API
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=replace_me
LLM_TRANSLATION_MODEL=deepseek-chat
LLM_REVIEW_MODEL=deepseek-chat

# GitHub
GITHUB_TOKEN=replace_me
GITHUB_BOT_OWNER=your-bot-owner-or-org

# 调度
SCHEDULER_ENABLED=true
```

---

# 8. SQLite：业务事实库

## 8.1 SQLite 规则

```text
SQLite 不存 embedding。
SQLite 不做 ANN 向量搜索。
SQLite 保存业务主数据和 Qdrant 同步任务。
```

SQLite 配置：

```python
# app/db/connection.py
import sqlite3

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(
        path,
        timeout=30,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
```

## 8.2 必要表

核心表：

```text
mods
source_snapshots
translation_units
translations
glossary_entries
tm_entries
jobs
feedback
pull_requests
vector_outbox
```

## 8.3 `tm_entries`

```sql
CREATE TABLE IF NOT EXISTS tm_entries (
  id TEXT PRIMARY KEY,

  source_text TEXT NOT NULL,
  normalized_source TEXT NOT NULL,
  target_text TEXT NOT NULL,

  context_type TEXT NOT NULL,
  mod_id TEXT REFERENCES mods(id),

  quality_tier TEXT NOT NULL,
  quality_score REAL NOT NULL,

  source_type TEXT NOT NULL,
  source_ref TEXT,
  source_hash TEXT NOT NULL,

  qdrant_point_id TEXT,
  qdrant_collection TEXT,
  vector_status TEXT NOT NULL DEFAULT 'pending',

  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

  UNIQUE(source_hash, target_text, context_type)
);
```

质量层级：

```text
official
human_verified
feedback_verified
ai_candidate
deprecated
```

只有前三类可以进入正式 Qdrant collection：

```text
official
human_verified
feedback_verified
```

## 8.4 `vector_outbox`

Qdrant 与 SQLite 不是同一个事务，因此需要 Outbox。

```sql
CREATE TABLE IF NOT EXISTS vector_outbox (
  id TEXT PRIMARY KEY,

  operation TEXT NOT NULL,
  tm_entry_id TEXT NOT NULL REFERENCES tm_entries(id),

  payload_json TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,

  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_vector_outbox_pending
ON vector_outbox(status, created_at);
```

操作类型：

```text
upsert
delete
reindex
```

写入规则：

```text
在 SQLite 中创建或更新 tm_entries 的同一个事务内，
必须插入一条 vector_outbox 记录。

worker 再读取 vector_outbox：
- 生成 embedding
- upsert / delete Qdrant point
- 成功后标记 completed
- 失败则 retry
```

这样可以避免：

```text
SQLite 已有翻译记忆，但 Qdrant 没写进去。
Qdrant 已更新，但 SQLite 状态丢失。
服务器重启后不知道哪些向量未同步。
```

## 8.5 SQLite FTS5

SQLite 继续保留 FTS5，但只用于词法检索通道：

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS tm_fts
USING fts5(
  tm_entry_id UNINDEXED,
  normalized_source,
  context_type UNINDEXED,
  tokenize='unicode61'
);
```

FTS5 索引的内容必须与正式 TM 一致：

```text
只有正式 tier 的 enabled 条目进入 FTS。
ai_candidate 不进 FTS。
deprecated 不进 FTS。
```

---

# 9. Qdrant Collection 设计

## 9.1 Collection 命名

建议按 embedding 模型与 schema 版本命名：

```text
tm_bge_m3_v1
```

不要使用：

```text
translation_memory
```

原因：

```text
未来换模型、换归一化规则或换向量维度时，不能混入旧向量。
```

升级时新建：

```text
tm_bge_m3_v2
tm_new_embedding_model_v1
```

全部重建完后再切换 `.env` 中的 `QDRANT_COLLECTION`。

## 9.2 Point 设计

一个正式翻译记忆对应一个 Qdrant Point。

```text
Point ID = tm_entries.qdrant_point_id
Vector   = normalized_source 的 bge-m3 dense embedding
Payload  = 可过滤元数据
```

Qdrant payload 只保存检索所需的最小元数据：

```json
{
  "tm_id": "tm_...",
  "context_type": "joker_description_line",
  "mod_scope": "global",
  "quality_tier": "official",
  "token_signature": "style:mult|var:1|reset",
  "source_lang": "en",
  "target_lang": "zh-CN",
  "embedding_model": "BAAI/bge-m3",
  "schema_version": 1
}
```

不建议将全部中文译文与完整审计信息都复制到 Qdrant。

原因：

```text
SQLite 是事实源。
Qdrant payload 越小，越容易同步、过滤和重建。
命中后根据 tm_id 回 SQLite 读取完整数据。
```

## 9.3 Payload Index

在写入任何 point **之前**创建 payload index：

```text
context_type
mod_scope
quality_tier
token_signature
source_lang
target_lang
embedding_model
```

这些字段都是 keyword。

Qdrant payload index 应在数据导入前完成，以便过滤检索与 HNSW 索引一起优化。

## 9.4 Collection 初始化代码

```python
# app/rag/qdrant_store.py
from qdrant_client import QdrantClient, models

PAYLOAD_KEYWORD_FIELDS = (
    "context_type",
    "mod_scope",
    "quality_tier",
    "token_signature",
    "source_lang",
    "target_lang",
    "embedding_model",
)

def ensure_tm_collection(
    client: QdrantClient,
    *,
    collection_name: str,
    vector_size: int,
) -> None:
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    for field_name in PAYLOAD_KEYWORD_FIELDS:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )
```

注意：

```text
向量维度不要写死。
程序启动时用 embedding 模型对一个测试文本编码，并读取 len(vector)。
该值用于创建 collection。
```

---

# 10. 本地 GPU Embedding

## 10.1 模型

默认：

```text
BAAI/bge-m3
```

用途：

```text
对 normalized_source 生成 dense embedding。
```

BGE-M3 支持多语言、dense retrieval、sparse retrieval 和 multi-vector retrieval；本项目 MVP 先使用 dense retrieval，之后再可升级 sparse hybrid。

## 10.2 标准化后再 embedding

原文：

```text
Gain {C:mult}+#1#{} Mult when played
```

不要直接 embedding 原文。

标准化后：

```text
gain <style_mult><var_1><style_reset> mult when played
```

原因：

```text
不同样式色彩不是语义差异。
变量数字变化不应该改变句式相似度。
统一 Token 后，RAG 更容易找到同模板句子。
```

## 10.3 Embedding 实现

```python
# app/rag/embeddings.py
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(
        self,
        model_name: str,
        device: str = "cuda",
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)
        probe = self.encode(["embedding dimension probe"])
        self.dimension = int(probe.shape[1])

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vectors.astype(np.float32, copy=False)
```

## 10.4 Qdrant Upsert

```python
from qdrant_client import models

def upsert_tm_point(
    client,
    collection_name: str,
    *,
    point_id: str,
    vector,
    payload: dict,
) -> None:
    client.upsert(
        collection_name=collection_name,
        points=[
            models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload=payload,
            )
        ],
        wait=True,
    )
```

## 10.5 批量同步

embedding 不应一条一条推理。

推荐 worker 批量流程：

```text
读取 32～128 条 pending vector_outbox
→ 批量生成 embedding
→ 组装 Qdrant points
→ 单次批量 upsert
→ SQLite 标记完成
```

初始 batch size：

```text
embedding：32
reranker：16
```

实际值以显存为准。

```text
显存不足：
先调小 batch size。
不要先换掉整个模型。
```

---

# 11. 本地 GPU Reranker

## 11.1 模型

默认：

```text
BAAI/bge-reranker-v2-m3
```

职责：

```text
将 Qdrant / FTS 召回的候选翻译记忆重新排序。
```

embedding 只能说“语义大致相似”，reranker 更适合判断：

```text
这个历史英文句子是否真的能作为当前句子的翻译参考？
```

## 11.2 Reranker 实现

```python
# app/rag/reranker.py
from FlagEmbedding import FlagReranker


class LocalReranker:
    def __init__(self, model_name: str) -> None:
        self.model = FlagReranker(
            model_name,
            use_fp16=True,
        )

    def score(self, query: str, candidates: list[str]) -> list[float]:
        pairs = [[query, candidate] for candidate in candidates]
        scores = self.model.compute_score(
            pairs,
            normalize=True,
        )
        return [float(score) for score in scores]
```

## 11.3 不要对太多候选 rerank

推荐：

```text
Qdrant dense：30 条
FTS5 lexical：20 条
合并去重后：最多 24 条
rerank：24 条
最终送给 LLM：最多 4 条
```

这样 GPU 负担稳定，Prompt 不会被冗余案例淹没。

---

# 12. RAG 完整链路

## 12.1 翻译单元输入

原始 Lua：

```lua
text = {
  "Gain {C:mult}+#1#{} Mult",
  "for every {C:attention}Joker{}"
}
```

提取出的第一条：

```json
{
  "unit_id": "unit_...",
  "unit_key": "descriptions.Joker.j_example.text[0]",
  "source_text": "Gain {C:mult}+#1#{} Mult",
  "context_type": "joker_description_line",
  "tokens": [
    "{C:mult}",
    "+#1#",
    "{}"
  ]
}
```

## 12.2 输入预处理

```text
source_text
→ 提取不可变 Token
→ 得到 normalized_source（给 embedding / 检索）
→ 得到 prompt_source（给 LLM）
→ 得到 token_signature（给过滤 / 加分）
```

例子：

```text
source_text:
Gain {C:mult}+#1#{} Mult

normalized_source:
gain <style_mult><var_1><style_reset> mult

prompt_source:
Gain [[TOKEN_0]][[TOKEN_1]][[TOKEN_2]] Mult

token_signature:
style_mult|var_1|style_reset
```

## 12.3 第 0 层：术语硬约束

先加载术语：

```text
当前模组 required glossary
→ 全局 required glossary
→ 当前模组普通 glossary
→ 全局普通 glossary
```

例子：

```json
[
  {"source": "Joker", "target": "小丑牌", "required": true},
  {"source": "Mult", "target": "倍率", "required": true},
  {"source": "Chips", "target": "筹码", "required": true}
]
```

术语不是“参考建议”，而是翻译器和验证器的硬规则。

## 12.4 第 1 层：SQLite 精确翻译记忆

查询：

```sql
SELECT *
FROM tm_entries
WHERE normalized_source = ?
  AND context_type = ?
  AND enabled = 1
  AND quality_tier IN (
    'official',
    'human_verified',
    'feedback_verified'
  )
ORDER BY quality_score DESC
LIMIT 3;
```

作用：

```text
若完全相同英文曾经高质量翻译过，优先复用。
```

## 12.5 第 2 层：Qdrant Dense Retrieval

Qdrant 是 RAG 的主检索通道。

建议分三路搜索：

```text
Lane A：当前模组 + 相同 context_type
Lane B：全局记忆 + 相同 context_type
Lane C：全局记忆 + 放宽 context_type
```

三个 lane 都用当前 `normalized_source` 的 BGE-M3 dense embedding 查询。

### Lane A

用途：

```text
优先复用同一模组已稳定的表达与专有名称。
```

Qdrant filter 逻辑：

```text
mod_scope = mod:<mod_id>
context_type = 当前 context_type
quality_tier ∈ {official, human_verified, feedback_verified}
source_lang = en
target_lang = zh-CN
embedding_model = BAAI/bge-m3
```

### Lane B

用途：

```text
复用全局同类型句式。
```

filter：

```text
mod_scope = global
context_type = 当前 context_type
```

### Lane C

用途：

```text
当完全同类型没有样本时，放宽 context_type，避免无参考。
```

filter：

```text
mod_scope = global
```

### Qdrant 查询代码骨架

```python
from qdrant_client import models

def search_dense(
    client,
    *,
    collection_name: str,
    vector: list[float],
    context_type: str | None,
    mod_scope: str | None,
    limit: int,
):
    must = [
        models.FieldCondition(
            key="source_lang",
            match=models.MatchValue(value="en"),
        ),
        models.FieldCondition(
            key="target_lang",
            match=models.MatchValue(value="zh-CN"),
        ),
        models.FieldCondition(
            key="embedding_model",
            match=models.MatchValue(value="BAAI/bge-m3"),
        ),
    ]

    if context_type:
        must.append(
            models.FieldCondition(
                key="context_type",
                match=models.MatchValue(value=context_type),
            )
        )

    if mod_scope:
        must.append(
            models.FieldCondition(
                key="mod_scope",
                match=models.MatchValue(value=mod_scope),
            )
        )

    result = client.query_points(
        collection_name=collection_name,
        query=vector,
        query_filter=models.Filter(must=must),
        limit=limit,
        with_payload=True,
    )
    return result.points
```

> 当前 qdrant-client 版本的参数命名应以安装版本的类型提示为准；核心结构是 `query_points + Filter + payload`。

## 12.6 第 3 层：SQLite FTS5 词法召回

向量搜索擅长语义，但有时会弱化关键词差异：

```text
owned
held
played
discarded
scored
```

因此保留 FTS5 通道。

查询应使用去除 Token 后的关键英文词，避免特殊符号干扰：

```sql
SELECT tm_entry_id, bm25(tm_fts) AS score
FROM tm_fts
WHERE tm_fts MATCH ?
LIMIT 20;
```

## 12.7 第 4 层：融合

将以下候选合并：

```text
exact hits
Qdrant Lane A
Qdrant Lane B
Qdrant Lane C
SQLite FTS5
```

使用 Reciprocal Rank Fusion（RRF）：

```text
RRF_score = Σ 1 / (k + rank_i)
```

MVP 建议：

```text
k = 60
```

RRF 的优点：

```text
不要求 Qdrant score 和 BM25 score 数值可直接比较。
只利用每个通道中的排序位置。
```

## 12.8 第 5 层：SQLite 回填与确定性过滤

Qdrant 返回 `tm_id` 后，回 SQLite 读取完整记录。

然后过滤：

```text
enabled = 1
quality_tier 为正式 tier
Token 模式兼容
目标中文不为空
source / target 语言正确
未被标记 deprecated
```

Token 模式不兼容时：

```text
不一定直接丢弃。
可以降低候选分数。
```

例如：

```text
当前：<var_1>
候选：<var_1><var_2>
→ 可参考句式，但不能作为强模板。
```

## 12.9 第 6 层：GPU Rerank

输入：

```text
query = 当前 normalized_source
candidate = 每条候选 normalized_source
```

reranker 对最多 24 条候选进行评分。

最终初始排序公式：

```text
final_score =
  0.55 × reranker_score
+ 0.20 × RRF_score_normalized
+ 0.15 × tm_quality_score
+ 0.05 × context_match
+ 0.05 × token_pattern_match
```

这是 MVP 的初始启发式，后续应通过评测集调整。

## 12.10 第 7 层：多样性筛选

最终最多取 4 条送给 LLM。

规则：

```text
最多 1 条几乎相同的模板。
最多 2 条相同 context_type 的同模组样本。
同一 source_hash 只保留 1 条。
优先级：official > human_verified > feedback_verified。
若 final_score 低于阈值，不提供参考，允许纯 LLM 翻译。
```

推荐阈值：

```text
>= 0.88：强参考
0.72 ～ 0.88：普通参考
< 0.72：不进入 Prompt
```

## 12.11 RAG Trace

每一条翻译必须记录检索溯源：

```json
{
  "normalized_source": "gain <style_mult><var_1><style_reset> mult",
  "exact_hits": ["tm_0001"],
  "qdrant_lane_a": [
    {"tm_id": "tm_0001", "score": 0.95}
  ],
  "qdrant_lane_b": [
    {"tm_id": "tm_0028", "score": 0.86}
  ],
  "fts_hits": ["tm_0001", "tm_0042"],
  "reranked": [
    {"tm_id": "tm_0001", "score": 0.98},
    {"tm_id": "tm_0028", "score": 0.79}
  ],
  "selected_examples": ["tm_0001", "tm_0028"],
  "glossary_ids": ["gl_003", "gl_014"]
}
```

这可以回答：

```text
为什么译成这样？
它参考了哪几条翻译？
某个错误是由哪一条低质量记忆带来的？
```

---

# 13. 翻译记忆数据导入

## 13.1 数据来源层级

```text
Tier 1：官方游戏中英文对照
Tier 2：可信人工精翻模组中英文对照
Tier 3：AI 严格验证后的用户反馈
Tier 4：普通 AI 自动译文
Tier 5：过期 / 低质量 / 冲突内容
```

Qdrant 正式 collection 只收：

```text
Tier 1
Tier 2
Tier 3
```

绝不直接收：

```text
Tier 4
Tier 5
```

## 13.2 导入清单

`seed/translation_memory/manifest.json`：

```json
[
  {
    "source_id": "official-base-game",
    "source_type": "official_game",
    "repo_url": "GitHub 仓库地址",
    "commit_sha": "固定 commit SHA",
    "en_paths": ["localization/en-us.lua"],
    "zh_paths": ["localization/zh_CN.lua"],
    "quality_tier": "official"
  },
  {
    "source_id": "curated-mod-a",
    "source_type": "community_mod",
    "repo_url": "GitHub 仓库地址",
    "commit_sha": "固定 commit SHA",
    "en_paths": ["localization/en-us.lua"],
    "zh_paths": ["localization/zh_CN.lua"],
    "quality_tier": "human_verified"
  }
]
```

## 13.3 导入步骤

```text
1. Clone 对应仓库并 checkout 固定 commit。
2. 英文和中文文件都用同一套 Lua extractor 解析。
3. 按 unit_key 对齐中英文。
4. 输出对齐报告。
5. 进行 Token 一致性检查。
6. 清洗无效条目。
7. 规范化 source_text。
8. 计算质量分。
9. 写入 SQLite tm_entries。
10. 写 vector_outbox。
11. worker 用 GPU 批量 embedding。
12. worker upsert 至 Qdrant。
13. 完成后更新 vector_status。
```

## 13.4 自动清洗条件

以下内容不应进入 TM：

```text
空字符串
只有 Token 的字符串
纯 Lua 代码
仅数字或符号
英文 / 中文任一为空
Token 不一致
乱码
调试文本
无法定位的 key
```

## 13.5 自动质量门

`human_verified` 也不能盲信。

建议：

```text
official：
  通过结构检查即可进入正式 TM。

human_verified：
  通过结构检查 + AI 评审。
  >= 0.90：正式 TM。
  0.75～0.89：候选，不进 Qdrant。
  < 0.75：拒绝。
```

评分组成：

```text
40%：AI 语义一致性
25%：术语一致性
20%：Token / 结构安全
15%：同一来源风格一致性
```

---

# 14. Lua 无损处理

## 14.1 绝对禁止整文件 LLM 输出

错误做法：

```text
把整份 en.lua 丢给模型，让模型输出 zh_CN.lua。
```

正确做法：

```text
Lua 原文件
→ Python 定位字符串字节范围
→ LLM 只返回 unit_id → translation
→ Python 从后向前替换字符串内部
→ LuaJIT 编译校验
```

## 14.2 双层解析

```text
Tree-sitter Lua：
- 基础结构辅助解析
- 识别 table / field / string 区域

无损 lexer / span locator：
- 精确记录 byte_start / byte_end
- 保留注释、缩进、引号、逗号、空格
- 生成可安全写回的 byte span
```

## 14.3 Token 保护

锁定：

```text
{C:mult}
{C:attention}
{X:...}
{}
#1#
#2#
#10#
\n
\"
\\
```

模型看到：

```text
Gain [[TOKEN_0]][[TOKEN_1]][[TOKEN_2]] Mult
```

模型只能返回同样的 Token 序列。

## 14.4 校验顺序

```text
Pydantic JSON 校验
→ unit_id 集合校验
→ Token 全等校验
→ required glossary 校验
→ Lua 字符串转义校验
→ 无损 patch
→ LuaJIT 编译
→ 白名单 diff 校验
```

任何一步失败：

```text
不发布。
```

---

# 15. LLM 翻译与 AI 评审

## 15.1 翻译器职责

输入：

```text
当前英文
Token 占位符
术语库
RAG 参考案例
context_type
模组名称
```

输出：

```json
{
  "translations": [
    {
      "id": "unit_001",
      "translation": "获得 [[TOKEN_0]][[TOKEN_1]][[TOKEN_2]] 倍率"
    }
  ]
}
```

禁止：

```text
解释
Markdown
思考过程
原文复述
多余字段
Lua 文件整体
```

## 15.2 翻译 System Prompt

```text
你是 Balatro 模组简体中文本地化翻译器。

规则：
1. 仅翻译自然语言。
2. 所有 [[TOKEN_n]] 必须原样保留，数量、名称、顺序完全一致。
3. required glossary 为硬约束，必须采用指定译法。
4. 参考案例用于学习术语、句式和风格，不得照抄不相关内容。
5. 中文应简洁、自然、适合游戏 UI。
6. 不输出 Markdown、分析、解释或代码块。
7. 只输出符合 JSON Schema 的 JSON。
```

## 15.3 独立 AI 评审

翻译器不能自己给自己判分。

评审器独立输入：

```text
英文
候选中文
Token
术语
RAG 案例
上下文
```

输出：

```json
{
  "semantic_score": 92,
  "terminology_score": 100,
  "style_score": 88,
  "decision": "accept",
  "issues": []
}
```

决策：

```text
Token 不通过：reject。
术语不通过：revise。
semantic >= 85 且 decision=accept：publish。
70～84：把 issues 带回翻译器自动重译一次。
连续两次未通过：degraded。
```

`degraded`：

```text
保留英文，或使用最安全候选。
不进入正式 TM。
等待未来用户反馈纠偏。
```

---

# 16. 用户反馈自动闭环

## 16.1 反馈必须精确定位

用户提交：

```text
mod_id
unit_id
translation_id
feedback_type
suggested_text
comment
```

问题类型：

```text
semantic_error
term_inconsistent
unnatural
format_error
untranslated
other
```

## 16.2 反馈执行流程

```text
POST /feedback
→ feedback 表新增 pending
→ 创建 evaluate_feedback job
→ worker 加载英文 / 当前中文 / 术语 / RAG / 历史版本
→ AI 判断反馈是否有效
→ 生成候选修订译文
→ Token / 术语 / Lua / AI review
→ 自动更新当前模组
→ Git 提交 Fork
→ 满足门槛后才晋升正式 TM
```

## 16.3 自动采纳当前模组

```text
feedback_valid >= 0.90
AND Token 校验通过
AND required glossary 不冲突
AND 新译文 AI 评审分比旧译文高至少 8 分
→ 自动采纳
```

## 16.4 进入 Qdrant 正式 TM 的门槛

```text
feedback_valid >= 0.92
AND 新译文 AI 评审分 >= 90
AND 非模组专属梗 / 专名
AND 满足至少一个：
  - 两位独立反馈者提出同义修正
  - 与官方 / 人工高质量案例高度一致
  - 原译文被 AI 明确判定为语义错误
→ quality_tier = feedback_verified
→ 写 vector_outbox
→ embedding
→ Qdrant upsert
```

---

# 17. 任务系统

## 17.1 不引入 Redis / Celery

MVP 使用：

```text
SQLite jobs 表
+ 单个 Python worker
+ APScheduler
```

理由：

```text
重启不丢任务。
状态、重试、错误都可查。
不增加 Redis / RabbitMQ 运维。
```

## 17.2 任务类型

```text
check_upstream
sync_repository
extract_units
translate_batch
review_translation
sync_vector_outbox
reindex_qdrant
publish_fork
update_pr
evaluate_feedback
backup
```

## 17.3 幂等键

| 任务 | idempotency_key |
|---|---|
| 上游检查 | `check:<mod_id>:<time_bucket>` |
| 同步提交 | `sync:<mod_id>:<commit_sha>` |
| 翻译批次 | `translate:<mod_id>:<commit_sha>:zh_CN` |
| 向量同步 | `vector:<tm_entry_id>:<collection>` |
| Qdrant 重建 | `reindex:<collection>:<schema_version>` |
| Fork 发布 | `publish:<mod_id>:<commit_sha>:zh_CN` |
| PR 更新 | `pr:<mod_id>:bot/zh-cn` |
| 反馈判断 | `feedback:<feedback_id>` |

## 17.4 Worker 运行

```bash
uv run python -m app.worker
```

MVP 只启动一个写 worker。

这样 SQLite 的写锁更容易控制。

---

# 18. GitHub 自动化

## 18.1 模组配置

`seed/mod_configs/example_mod.yaml`：

```yaml
id: example_mod

origin:
  owner: upstream-owner
  repo: example-mod
  branch: main

fork:
  owner: your-bot-owner
  repo: example-mod

publish_mode: fork_only

source_locale_paths:
  - localization/en-us.lua
  - localization/en.lua

target_locale_path: localization/zh_CN.lua

poll_minutes: 360
parser_profile: steamodded_lua_v1
```

## 18.2 发布模式

```text
fork_only：
  只更新自己的 Fork。

upstream_pr：
  更新 Fork，并创建 / 更新原作者仓库 PR。

disabled：
  只监控，不执行翻译与发布。
```

## 18.3 同步流程

```text
GitHub API 检查最新 commit
→ 与 last_seen_sha 对比
→ 若变化则创建 sync job
→ git fetch upstream
→ checkout 指定 commit
→ 提取英文 unit
→ 与上一 snapshot 按 unit_key + source_hash 对比
→ 只翻译 new / changed unit
→ patch zh_CN.lua
→ Lua 校验
→ git commit
→ git push bot/zh-cn
→ 可选 PR 创建 / 更新
```

## 18.4 不自动合并

机器人只做：

```text
提交 Fork
创建 PR
更新 PR
```

机器人不做：

```text
自动合并上游作者仓库。
```

---

# 19. 本地服务进程

## 19.1 开发模式

```bash
# API
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# worker
uv run python -m app.worker

# scheduler
uv run python -m app.scheduler
```

## 19.2 生产模式建议

服务端使用 systemd 保持三个 Python 进程：

```text
balatro-cn-api.service
balatro-cn-worker.service
balatro-cn-scheduler.service
```

Qdrant 用 Docker Compose 启动并设置：

```text
restart: unless-stopped
```

FastAPI 如需对外开放：

```text
Nginx / Caddy 反向代理
HTTPS
只暴露 Web 页面与 FastAPI
绝不直接暴露 Qdrant 6333 / 6334
```

---

# 20. 备份与恢复

## 20.1 事实源优先

恢复顺序：

```text
1. 恢复 SQLite。
2. 恢复 Git 工作目录或重新 clone。
3. 重新构建 Qdrant collection。
```

Qdrant 是可再生检索层，因此：

```text
SQLite 备份优先级最高。
Qdrant snapshot 用于更快恢复，不应成为唯一备份。
```

## 20.2 SQLite 备份

```bash
mkdir -p data/backups
sqlite3 data/balatro_cn.db \
  ".backup 'data/backups/balatro_cn-$(date +%F-%H%M%S).db'"
```

## 20.3 Qdrant Snapshot

建议定时创建 collection snapshot。

逻辑：

```text
每天：
1. 让 worker 完成当前 vector_outbox。
2. 调 Qdrant 创建 snapshot。
3. 将 snapshot 文件复制到独立磁盘或对象存储。
4. 保留最近 7～30 个版本。
```

## 20.4 灾难恢复

```text
SQLite 可用，Qdrant 丢失：
→ 执行 `reindex-qdrant --collection tm_bge_m3_v1`

SQLite 丢失，Qdrant 可用：
→ 不建议直接从 Qdrant 恢复完整业务；
→ 从备份恢复 SQLite。

两者都丢失：
→ 恢复 Git / seed 数据
→ 重新导入 TM
→ 重新建立 embedding 与 Qdrant。
```

---

# 21. 评测与质量监控

## 21.1 独立评测集

目录：

```text
seed/eval_cases/
```

评测集绝不能：

```text
参与 Qdrant collection
参与 FTS5
进入 RAG Prompt
```

每条：

```json
{
  "id": "eval_0001",
  "source": "Gain #1# Mult",
  "expected": "获得 #1# 倍率",
  "context_type": "joker_description_line",
  "required_glossary": [
    {"source": "Mult", "target": "倍率"}
  ],
  "tokens": ["#1#"]
}
```

## 21.2 RAG 指标

```text
Recall@30：
正确参考是否进入 Qdrant + FTS 的候选集合。

Rerank@4：
正确参考是否进入最终 4 条 Prompt 参考。

MRR：
正确参考平均排位。

Low-quality retrieval rate：
低质量 / 不兼容样本被送入 Prompt 的比例。
```

## 21.3 翻译指标

```text
Token 保留率：100%
Lua 可编译率：100%
非翻译区域改动率：0%
术语硬约束遵守率：>= 99%
结构化 JSON 成功率：>= 99%
AI 盲评语义分
用户反馈采纳后的质量提升
```

## 21.4 修改后必须回归

以下任一变化后：

```text
Token 规则
Lua patcher
embedding 模型
Qdrant collection schema
RAG 融合策略
reranker
Prompt
术语库
```

都执行：

```bash
uv run pytest -q
uv run python -m app.cli.main evaluate
```

---

# 22. 实施阶段

## 阶段 A：文件安全

```text
[ ] Lua 无损字符串定位
[ ] unit_key 生成
[ ] Token 保护与恢复
[ ] 逆序 span patch
[ ] LuaJIT 编译
[ ] 白名单 diff
[ ] fixture 测试
```

验收：

```text
不依赖 LLM，也能保证：
翻译文本替换外，其他字节不变。
```

## 阶段 B：无 RAG 翻译闭环

```text
[ ] LLM client
[ ] JSON Schema 校验
[ ] glossary 硬约束
[ ] AI review
[ ] 自动重译
[ ] translation version history
```

验收：

```text
选一个小模组，可以无人审核生成安全 zh_CN.lua。
```

## 阶段 C：Qdrant 与本地 GPU RAG

```text
[ ] Docker Compose 启动 Qdrant
[ ] qdrant-client
[ ] BGE-M3 GPU embedding
[ ] tm_entries + vector_outbox
[ ] collection 创建
[ ] payload index
[ ] 只同步正式 TM
[ ] exact + Qdrant + FTS 检索
[ ] RRF
[ ] reranker
[ ] retrieval trace
```

验收：

```text
每条翻译可查到参考案例。
相似句式能够稳定复用高质量表达。
```

## 阶段 D：GitHub 自动维护

```text
[ ] mod YAML
[ ] APScheduler
[ ] upstream commit 检测
[ ] 本机 git sync
[ ] 增量翻译
[ ] Fork push
[ ] 可选 PR 更新
```

验收：

```text
上游英文改变后，本机自动更新 Fork。
```

## 阶段 E：反馈自动闭环

```text
[ ] FastAPI feedback API
[ ] feedback worker
[ ] AI feedback judge
[ ] 自动修正当前模组
[ ] 受控升级 feedback_verified
[ ] Qdrant 自动同步
[ ] 版本回滚
```

验收：

```text
用户提交有效反馈后，无人工审核即可修正对应翻译。
```

---

# 23. 常用命令

```bash
# 启动 Qdrant
docker compose up -d

# 初始化 SQLite
uv run python -m app.db.migrate

# 导入初始高质量 TM
uv run python -m app.cli.main import-tm \
  --manifest seed/translation_memory/manifest.json

# 同步 SQLite 正式 TM 到 Qdrant
uv run python -m app.cli.main sync-vectors

# 全量重建指定 collection
uv run python -m app.cli.main reindex-qdrant \
  --collection tm_bge_m3_v1

# 查询 Qdrant collection 统计
uv run python -m app.cli.main qdrant-status

# 检查指定模组
uv run python -m app.cli.main check-mod \
  --mod-id example_mod

# 手动完整同步
uv run python -m app.cli.main sync-mod \
  --mod-id example_mod

# worker
uv run python -m app.worker

# scheduler
uv run python -m app.scheduler

# API
uv run uvicorn app.api.main:app \
  --host 127.0.0.1 \
  --port 8000

# 运行测试
uv run pytest -q

# 跑 RAG / 翻译评测
uv run python -m app.cli.main evaluate
```

---

# 24. 最终验收标准

```text
[ ] Qdrant 在自建服务器 Docker 中稳定运行。
[ ] Qdrant 端口不直接暴露公网。
[ ] Qdrant API key 已启用。
[ ] SQLite 作为业务事实源。
[ ] 正式 TM 向量只存入 Qdrant。
[ ] ai_candidate 不进入 Qdrant 正式检索 collection。
[ ] embedding 使用本地 GPU。
[ ] reranker 使用本地 GPU。
[ ] RAG 至少包含 exact + Qdrant dense + FTS5 + rerank。
[ ] 每条翻译都有 retrieval trace。
[ ] Token 变量保留率 100%。
[ ] Lua 编译通过率 100%。
[ ] 上游更新可本机自动同步。
[ ] 用户反馈可自动评估与自动修正。
[ ] 有效反馈仅在高门槛下进入正式 Qdrant TM。
[ ] SQLite 与 Qdrant 都有可执行的备份 / 恢复流程。
```

---

# 25. 关键原则总结

```text
SQLite 不做向量数据库。
Qdrant 不做业务主数据库。
GPU 不给 Qdrant，用于 embedding 和 rerank。
LLM 不负责文件结构。
Python 不把整份 Lua 交给模型。
普通 AI 译文不直接进入 RAG。
用户反馈不直接污染 Qdrant。
```

最终正确关系：

```text
SQLite：真实数据、版本、状态、反馈、审计。
Qdrant：高质量翻译记忆的向量检索。
GPU：本地语义模型推理。
LLM：翻译与语言判断。
Python：所有确定性控制。
```

---

# 26. 官方资料对应关系

```text
Qdrant：
- Local Quickstart：Docker、Python Client、Collection、Query。
- Security：自建实例必须显式启用认证，避免公网暴露。
- Indexing：payload index 应优先于数据导入创建。
- Snapshots：collection / storage 备份与恢复。

BAAI：
- BGE-M3：多语言 embedding，支持 dense / sparse / multi-vector；推荐 hybrid retrieval + reranking。
- bge-reranker-v2-m3：本地 multilingual reranker，适合候选二次排序。
```
