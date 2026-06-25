# 当前翻译流程与项目进度

更新日期：2026-06-25

本文记录当前代码已经实现的 Balatro 模组中文本地化流程、关键设计取舍、预览 JSONL 契约，以及下一步生成 `zh_CN.lua` 前必须满足的安全边界。

## 当前阶段

项目目前处于“知识库 + RAG 翻译预览”阶段：

- 已能从已有中英 Lua 本地化文件导入翻译记忆到 SQLite。
- 已能用 Ollama `qwen3-embedding:8b` 生成 embedding，并同步到 Qdrant。
- 已能对未翻译模组做 RAG 检索预览。
- 已能调用 OpenAI-compatible LLM API 生成 entry 级翻译预览 JSONL。
- 已能保护 Balatro token，校验 LLM 输出是否破坏 token。
- 已能根据中文视觉宽度重排 `text[]` / `unlock[]`。
- 已能标记哪些预览行能被当前 byte-level patcher 安全写回。

还没有完成：

- 从 entry preview 自动生成完整 `zh_CN.lua` 的命令。
- table-level Lua writer，也就是支持安全增删 `text[]` / `unlock[]` 行。
- 自动术语违规审查和自动重试。
- PR 自动创建与反馈闭环。

## 数据与服务

当前本地服务边界：

- SQLite：`data/balatro_cn.db`
- Qdrant：`http://127.0.0.1:6333`
- Qdrant collection：`tm_qwen3_embedding_8b_v1`
- Embedding：Ollama `qwen3-embedding:8b`
- LLM：通过 `LLM_BASE_URL` 使用 OpenAI-compatible `/chat/completions`

主要环境变量：

```bash
QDRANT_API_KEY=replace_me
LLM_API_KEY=replace_me
LLM_BASE_URL=https://api.openai.com/v1
LLM_TRANSLATION_MODEL=gpt-4.1-mini
LLM_CONCURRENCY=1
```

`LLM_CONCURRENCY` 默认是 `1`。CLI 的 `--concurrency` 会覆盖环境变量。

## 知识库流程

知识库以 SQLite 作为事实源，以 Qdrant 作为可重建的向量索引。

1. `migrate` 初始化 SQLite schema。
2. `import-local-tm` 解析已翻译模组的英文 Lua 和中文 Lua。
3. 导入时按相同 `unit_key` 对齐 source/target。
4. token 不一致的条目会被跳过，避免污染翻译记忆。
5. 合格条目写入 `tm_entries`，并写入 `vector_outbox`。
6. `sync-vectors` 读取 outbox，调用 Ollama embedding，再 upsert 到 Qdrant。
7. `search` 和 preview 命令通过 Qdrant 取回相似翻译记忆。

当前已经验证过的知识库中包含原版术语，例如：

```text
Negative -> 负片
Negative Tag -> 负片标签
{C:dark_edition}Negative{} copy -> {C:dark_edition}负片{}版本的复制牌
```

## Entry 级翻译流程

推荐命令：

```bash
bash -lc 'set -a; source .env; set +a; uv run --frozen python -m app.cli.main translate-entry-preview-mod \
  --repo data/repos/EricTheToon__Fortlatro/Fortlatro \
  --source localization/default.lua \
  --limit 20 \
  --top-k 5 \
  --max-width 18 \
  --concurrency 4 \
  --output data/artifacts/fortlatro_entry_translate_preview.jsonl'
```

流程：

1. `LuaExtractor` 从源 Lua 中提取 `TranslationUnit`。
2. `group_translation_units` 按 entry 聚合：
   - `name`
   - `text[]`
   - `unlock[]`
3. credit line 会从正文中拆出，不送给 LLM：
   - `Idea:`
   - `Art:`
   - `Code:`
   - `Concept:`
   - `Music:`
   - `Sound:`
   - `Credit:` / `Credits:`
4. RAG 检索 references。
5. LLM 按完整 entry 翻译，不按英文原行逐行翻译。
6. 程序恢复 token，并校验 token identity。
7. 程序按中文视觉宽度重排为 `text[]` / `unlock[]`。
8. credit line 原样追加回 `text[]`。
9. 写出 JSONL 预览，不修改 Lua。

## RAG 设计

当前不再只用整条描述做一次 dense search。

Entry 级 RAG 使用三层组合：

1. 多查询 dense RAG
   - 每个原始 `text[]` 行单独检索。
   - 再用 combined entry 作为 fallback query。
   - 多个 query 的结果 round-robin 去重合并，避免一个长句的主语义占满 top-k。

2. deterministic glossary
   - 从 styled span 中抽取术语，例如 `{C:dark_edition}Negative{}`。
   - 直接查 SQLite 翻译记忆中的精确术语或包含术语的人工翻译。
   - glossary refs 放在 dense refs 前面。

3. LLM prompt references
   - dense refs 和 glossary refs 合并后传给 translator。
   - JSONL 的 `rag_refs` 会保留最终送入 LLM 的参考。

这个设计解决了一个实际问题：Perkeo 描述中同时有 `Negative`、`consumable`、`shop` 等概念。只用整条 entry 做 dense query 时，top-k 容易召回 `consumable/shop`，却漏掉 `Negative -> 负片`。多查询和 glossary 能让每个关键概念都有独立召回机会。

## Token 策略

Balatro 本地化 token 包括：

```text
{C:mult}
{C:dark_edition}
{}
#1#
{X:mult,C:white}
{T:tag_negative}
```

当前策略：

- 传给 LLM 前先把 token 替换为 `[[TOKEN_n]]`。
- line 级翻译必须保持 token 顺序。
- entry 级翻译允许 token 重排，但必须每个 placeholder 出现且只出现一次。
- 恢复后会校验 token inventory，不能增删、改写 token。
- token restore 失败时，对应字段不会继续 reflow，避免把 `[[TOKEN_n]]` 写进候选译文。

允许 entry 级 token 重排是必要的，因为中文语序经常会把英文短语调换位置。例如 `at the end of the {C:attention}shop` 可以自然前置为“在{C:attention}商店结束时”。

## 中文重排策略

LLM 返回完整未换行中文字符串，程序负责换行。

当前 `reflow_zh_text`：

- CJK 字符按宽度 2 估算。
- ASCII 按宽度 1 估算。
- 样式 token `{...}` 宽度按 0 处理。
- 变量 token `#1#` 计入宽度。
- 不拆 Balatro token。
- 不拆 ASCII 单词，例如 `Sweaty`、`Stake`。
- 尽量避免中文标点出现在行首。

`--max-width` 推荐先用 `18`。`12` 对英文名、署名和混合 token 的文本太窄，容易牺牲可读性。

## Preview JSONL 契约

`translate-entry-preview-mod` 每行输出一个 entry：

```json
{
  "entry_key": "descriptions.Joker.j_perkeo",
  "ok": true,
  "patchable": false,
  "patch_warnings": ["text line count mismatch: source=4, target=3"],
  "target_units": {
    "name": "descriptions.Joker.j_perkeo.name",
    "text": [
      "descriptions.Joker.j_perkeo.text[0]",
      "descriptions.Joker.j_perkeo.text[1]"
    ],
    "unlock": []
  },
  "name": "Perkeo",
  "text": ["..."],
  "unlock": [],
  "token_errors": [],
  "source": {
    "name": "Perkeo",
    "text": ["..."],
    "unlock": []
  },
  "rag_refs": []
}
```

字段含义：

- `ok`: LLM 请求成功，且 token 校验通过。
- `patchable`: 当前 byte-level patcher 是否可以安全写回。
- `patch_warnings`: 不可直接写回的原因。
- `target_units`: 后续 patch 应该写入的 Lua unit_key。
- `source`: 源英文 entry，用于审查和 diff。
- `rag_refs`: 实际送给 LLM 的翻译记忆引用。

当前 byte-level patcher 只能替换已存在字符串内容，不能增删 Lua table 里的字符串项。因此：

- `ok=true && patchable=true` 可以进入当前安全写回流程。
- `ok=true && patchable=false` 说明译文可参考，但行数变化，必须等 table-level writer。
- `ok=false` 不能写回。

## 并发设计

`--concurrency` 只控制 LLM 请求并发，不并发写 JSONL。

当前行为：

- RAG 查询在主线程按 entry 顺序执行。
- 每个 LLM 任务创建独立 OpenAI-compatible client。
- LLM 完成日志按真实完成顺序输出。
- JSONL 仍按源 Lua entry 顺序写入。
- 单条失败会写出 `ok=false` / `error`，不会中断整个 preview。

这样既能利用 API 并发，也能保证预览文件顺序稳定，便于审查和后续 patch。

## 当前命令

知识库：

```bash
uv run python -m app.cli.main migrate
uv run python -m app.cli.main import-local-tm --repo ... --mod-id ... --source ... --target ...
uv run python -m app.cli.main sync-vectors --limit 100
uv run python -m app.cli.main search "Gain +#1# Mult" --top-k 5
```

预览：

```bash
uv run --frozen python -m app.cli.main rag-preview-mod --repo ... --source ...
uv run --frozen python -m app.cli.main translate-preview-mod --repo ... --source ... --output ...
uv run --frozen python -m app.cli.main translate-entry-preview-mod --repo ... --source ... --output ...
```

测试：

```bash
uv run --frozen pytest -q
```

## 已完成

- Worker-first 项目结构。
- YAML 配置和 `.env` 模板。
- Git proxy 配置。
- Qdrant Docker Compose。
- SQLite migrations。
- Lua extraction。
- token protection / restoration / validation。
- byte-level Lua patcher。
- LuaJIT compile validator。
- TM import。
- vector outbox sync。
- Qdrant retrieval CLI。
- RAG preview CLI。
- OpenAI-compatible LLM client。
- entry 级 translation preview。
- LLM base URL / model / concurrency env 配置。
- 多查询 RAG。
- deterministic glossary。
- 中文 reflow。
- preview patchability 标记。

## 下一步

建议按这个顺序推进：

1. `apply-entry-preview` 命令
   - 输入 preview JSONL。
   - 默认只写 `ok=true && patchable=true`。
   - 输出新的 `zh_CN.lua`，不覆盖源文件。
   - 打印 skipped report。

2. table-level Lua writer
   - 支持 `text[]` / `unlock[]` 行数变化。
   - 保留缩进、逗号、注释和周边结构。
   - 解决 Perkeo 这类 `source=4, target=3` 的写回问题。

3. 术语审查
   - 从 TM 和人工术语表生成 glossary。
   - 检查译文是否违反强制术语，例如 `Negative -> 负片`。
   - 失败时自动重试或标记 review needed。

4. 质量评审
   - AI reviewer 独立检查语义、风格、token、术语。
   - 对低质量候选做 retry。

5. GitHub PR 流程
   - 生成分支。
   - 写入 `zh_CN.lua`。
   - 运行 Lua validator。
   - 创建双语 PR body。
