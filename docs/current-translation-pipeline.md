# 当前翻译流程与项目进度

更新日期：2026-06-28

本文记录当前代码已经实现的 Balatro 模组中文本地化流程、关键设计取舍、预览 JSONL 契约，以及下一步生成 `zh_CN.lua` 前必须满足的安全边界。

翻译质量、模组级上下文、连续对话历史方案和下一阶段推荐架构见
[`docs/translation-quality-context-strategy.md`](translation-quality-context-strategy.md)。

## 当前阶段

项目目前处于“知识库 + RAG 翻译预览”阶段：

- 已能从已有中英 Lua 本地化文件导入翻译记忆到 SQLite。
- 已能用配置的 embedding provider 生成 embedding，并同步到 Qdrant；默认是
  Ollama `qwen3-embedding:8b`，也支持 OpenAI-compatible `/embeddings` API。
- 已能对未翻译模组做 RAG 检索预览。
- 已能调用 OpenAI-compatible LLM API 生成 entry 级翻译预览 JSONL。
- 已能保护 Balatro token，校验 LLM 输出是否破坏 token。
- 已能根据中文视觉宽度重排 `text[]` / `unlock[]`。
- 已能标记哪些预览行能被当前 byte-level patcher 安全写回。
- 已能使用预构建的原版 Balatro 中英风格包，让模组翻译贴近官方简中断句、语序和用词。
- 已能从 entry preview 生成新的 `zh_CN.lua`，并在 `--table-level` 模式下写回 `text[]` / `unlock[]` 行数变化。
- 已能先预翻译全模组 `name` 字段，生成 mod-wide EN/ZH 名称对照，并把该对照注入每个 entry 的 prompt。
- 已能用原版 Balatro 名称模式辅助新增名称翻译，例如由 `Blue/Gold/Purple/Red Seal -> *蜡封` 推断 `Seal -> 蜡封`，避免把 seal 误译成“封印”。
- 已能区分翻译质量状态 `needs_review` 与写回策略 `apply_mode`；中文自然换行导致的行数变化不再算质量问题。
- 已能用 `translate-entry-loop` 串起全量 preview、apply、audit、rerun、merge 和再次 audit，形成可重复的闭环；每轮产物和最终状态写入 manifest，便于验收后复盘。
- 已能维护模组级 `mod_translation_brief.json`，把已接受的 name 对照持久化下来，并在下一轮 preview/loop 中作为更高优先级上下文复用。
- 已能在 preview consistency 阶段复用同类别内完全相同 source body 的最佳译文，避免同一英文模板在不同 entry 中翻出多套断句/用词；rerun merge 后也会对完整 preview 再跑一次一致性收敛。
- 已能在 preview 阶段标记 `text[]` / `unlock[]` 中的 rerunnable 残留英文，例如 `lvl`、`Imaginary`、`Consumble`、`null`，避免这些坏译文直接进入 apply。
- 已能递归解析非标准顶层本地化表，例如 `Menus`、`ExtraEffects`；也会通过 LuaJIT 展开纯 localization 文件中由循环或变量生成的返回表字段，例如动态 `descriptions.Alphabet` 和 `misc.poker_hands`。

还没有完成：

- 完整终审 reviewer，用于全文件语义、风格和术语一致性检查。
- PR 自动创建与反馈闭环。

已完成（Phase 1 质量基础）：

- extractor 覆盖 `misc.dictionary` / `misc.labels` / `misc.quips`（含 `["$"]` 方括号键）。
- `scan-mod-terms` 生成模组级 name/label/styled term 候选表。
- `check-terms` 对 preview JSONL 做锁定术语违规审查。
- entry preview 内置锁定术语检查，输出 `needs_review` / `review` / `brief_version`。
- entry preview 内置一次 LLM 质量 reviewer；发现中文语序生硬或明显语义偏移时，会带 reviewer feedback 自动重译一次，并记录 `review.retry_history`。
- RAG 参考分层：locked glossary / same-context / loose，prompt 分段渲染。
- `build-style-pack` 可从 `Balatro__Origin` 预构建官方中英对照风格包，默认写入 `app/llm/assets/balatro_origin_style_pack.json`；当前资产包含 12 个 description 类别，每类至少 10 条参考。
- `apply-entry-preview` 可从 preview JSONL 生成新的 `zh_CN.lua`；默认只写安全子集，传 `--table-level` 时支持 `text[]` / `unlock[]` 行数变化。
- name prepass 会过滤明显误导的非原版跨类别 name 引用和单词级引用，并为 label-only 条目直接生成 name preview，避免空 body 被 LLM 生成说明文字后触发 token error。
- 初次 entry 翻译若出现 token mismatch，会带 token error feedback 自动 revision 一次；revision 仍有 token error 才保留失败。
- 模组级 translation brief 已接入 entry preview 和 loop：confirmed brief name/term 会压过当前批次 name prepass、context preview 和 RAG/style refs。

## 数据与服务

当前本地服务边界：

- SQLite：`data/balatro_cn.db`
- Qdrant：`http://127.0.0.1:6333`
- Qdrant collection：`tm_qwen3_embedding_8b_v1`
- Embedding：默认 Ollama `qwen3-embedding:8b`；也支持 OpenAI-compatible
  `/embeddings` API，例如 Gitee AI `Qwen3-Embedding-8B`
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

线上 embedding API 可通过 `config/app.yml` 切换：

```yaml
embedding:
  provider: openai-compatible
  base_url: https://ai.gitee.com/v1
  model: Qwen3-Embedding-8B
  batch_size: 16
  api_key_env: EMBEDDING_API_KEY
  dimensions: 4096
  instruction: "指令：用于 Balatro 汉化 translation memory 检索。"
  failover_enabled: true
```

`EMBEDDING_API_KEY` 放在 `.env` 或环境变量中；`failover_enabled` 会发送
`X-Failover-Enabled: true`。

## 知识库流程

知识库以 SQLite 作为事实源，以 Qdrant 作为可重建的向量索引。

1. `migrate` 初始化 SQLite schema。
2. `import-local-tm` 解析已翻译模组的英文 Lua 和中文 Lua。
3. 导入时按相同 `unit_key` 对齐 source/target。
4. token 不一致的条目会被跳过，避免污染翻译记忆。
5. 合格条目写入 `tm_entries`，并写入 `vector_outbox`。
6. `sync-vectors` 读取 outbox，调用配置的 embedding provider，再 upsert 到 Qdrant。
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
  --concurrency 1 \
  --output data/artifacts/fortlatro_entry_translate_preview.jsonl'
```

`--concurrency` 这里用 `1`，和 `LLM_CONCURRENCY` 默认值一致，也和 README 示例一致。当前已经有 frozen locked terms、批次内 name prepass、context preview seeds 和可选 `--brief`；并发大于 1 时同一批 entry 仍使用同一份冻结上下文，JSONL 输出顺序稳定。为了首批验收翻译质量，示例仍保守用 1；真实全量 loop 可以根据 API 稳定性提高并发。

流程：

1. `LuaExtractor` 从源 Lua 中提取 `TranslationUnit`。
   - 静态字面量会带 byte span，可参与安全 patch。
   - 运行时展开得到的动态字段会带 `byte_start=-1` / `byte_end=-1`，进入 preview/audit，但默认 `apply_mode=blocked`，避免把无法定位源码 span 的字段误写回。
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
5. 选择 style references：官方同类样例优先；原版没有的自定义类别从 SQLite TM 取同类已翻译样例；最后才用语义 fallback。
6. LLM 按完整 entry 翻译，不按英文原行逐行翻译。
7. 程序恢复 token，并校验 token identity；若初次结果 token mismatch，带 token error feedback 自动 revision 一次。
8. 读取 `--brief` 指定的模组级 translation brief；confirmed `name_map` 会先作为 name seed，覆盖 context preview 里的同名 seed。
9. 先翻译本批全部可用 `name` 字段，形成 mod-wide name glossary；同一英文 name 在本批出现多个译名时，优先采用 description entry 的译名并回填 label-only 条目，后续每个 entry prompt 都会带上这份对照。
10. 若 token 正常，LLM reviewer 检查中文语序、机械英文结构和明显语义偏移；如需修订，带 reviewer feedback 自动重译一次。
11. 程序按中文视觉宽度重排为 `text[]` / `unlock[]`。
12. credit line 原样追加回 `text[]`。
13. preview consistency 做 deterministic 后处理：
   - 同一 `descriptions.<Category>` 内完全相同的 source `text[]` / `unlock[]` 会复用最佳已接受译文，避免重复模板翻译不一致。
   - `text[]` / `unlock[]` 中的 rerunnable 残留英文会进入 `review.consistency_warnings`，并把 row 标成 `needs_review=true`。
   - `name` 残留英文仍留给 audit 汇总，避免只因短专名或缩写导致整条正文无法写回。
14. 根据 row 结构计算 `apply_mode`：
   - `unit`: 可以逐 unit 写回。
   - `table`: 只有 `text[]` / `unlock[]` 行数变化，需要 `--table-level`。
   - `blocked`: 结构不完整、LLM 失败或缺少必需字段，不能安全写回。
15. 写出 JSONL 预览，不修改 Lua。

name prepass 使用当前 entry 的 RAG/glossary refs，但会过滤容易污染名称的非原版跨类别引用。entry 的期望类别从 `descriptions.<Category>` 动态推导为 `<category>_name` / `<category>_description_line`，所以 Sleeve、Partner、Seal、Enhanced 等自定义类别不需要硬编码。精确同名引用只有来自 `balatro_origin` 或同 context 时才进入 name prompt；例如 Enhanced 的 `Gilded` 不应被 Partner 的 `Gilded -> 黄金伙伴` 带偏。复合名称中的非原版单词级引用也会被过滤，例如 `Gilded Seal` 不应被 `partner_api` 的 `Gilded -> 黄金伙伴` 带偏。它还会从 frozen locked term map 中提取原版组合词模式：如果存在多条 `* Seal -> *蜡封`，则向 name prompt 添加 `Seal -> 蜡封` 和若干 `Gold Seal -> 金色蜡封` 之类的同模式参考。

locked term checker 也保留 term 的 `context_type` / `mod_id` 元数据。`styled` term 仍按锁定术语检查；`exact` term 只有来自 `balatro_origin` 或同 context 时才触发 review，避免 Partner、Sleeve、Enhanced 等自定义类别之间的同名污染。

重跑问题 entry 时，`--context-preview` 会从旧 preview 中读取 `ok=true && needs_review=false` 的 name/label 对照。如果某个英文 name 在旧 preview 中只有一个中文译名，翻译器会把它作为 name prepass seed 直接复用；若旧 preview 自己已经多译，则不会自动选边，交由 audit 的 name inconsistency 处理。若同时传入 `--brief`，优先级为：confirmed brief name/term > 当前批次 name prepass > context preview seeds/context > RAG/style refs。

## 模组级 Translation Brief

`mod_translation_brief.json` 是模组级、可审计、可人工修改的状态文件，用来稳定同一模组内的译名和术语。`translate-entry-preview-mod --brief path/to/mod_translation_brief.json` 会读取它并把 confirmed `name_map` / `term_map` 注入 prompt；preview 命令只读 brief，不会自行更新它。

`translate-entry-loop` 默认使用 `<work-dir>/mod_translation_brief.json`，也可以通过 `--brief` 指定其他路径。loop 每轮完成 `apply-entry-preview` 和 `audit-entry-output` 后，会从已接受的 preview row 中提取 `ok=true && needs_review=false && apply_mode!=blocked` 的 name 对照，更新 brief 并写回磁盘。若同一个英文 name 已有 confirmed 译名但新结果不同，不会覆盖旧值，而是写入 `open_questions` 供人工处理。

brief 上下文的优先级高于临时上下文：

```text
confirmed brief name/term
> 当前批次 name prepass / mod-wide name glossary
> --context-preview 中的已接受译名
> locked glossary / same-context RAG / loose RAG / style refs
```

loop 的 `manifest.json` 会记录 `brief_path` 和当前 `brief_version`，便于复盘某轮输出使用了哪份模组状态。

## 风格参考

`app/llm/assets/balatro_origin_style_pack.json` 是预构建的官方 Balatro EN/ZH 对照资产，不在每次翻译时临时抽样。它由下面命令生成：

```bash
uv run --frozen python -m app.cli.main build-style-pack \
  --repo data/repos/Balatro__Origin \
  --source localization/en-us.lua \
  --target localization/zh_CN.lua \
  --output app/llm/assets/balatro_origin_style_pack.json \
  --min-per-category 10 \
  --max-per-category 1000
```

当前资产覆盖 `back`、`blind`、`edition`、`enhanced`、`joker`、`other`、`planet`、`spectral`、`stake`、`tag`、`tarot`、`voucher` 共 12 类，所有类别都满足每类至少 10 条。

entry preview 的 style references 组合顺序：

1. 官方风格包中相同 `descriptions.<Category>` 的样例。
2. SQLite TM 中相同 `context_type` 的已翻译样例，用于 `Sleeve`、`Partner`、`paperback_minor_arcana` 等原版没有的自定义类别。
3. 官方风格包 fallback，例如当前 `Sleeve` 可以 fallback 到 `Back`，但只有在 TM 同类样例不足时才补足。

命中某个条目时，会优先保留该条目的连续文本行，避免只拿零散相似句污染 prompt。例如 Perkeo 会把官方四行译法一起送入 prompt：

```text
Creates a {C:dark_edition}Negative{} copy of -> 在离开商店时
{C:attention}1{} random {C:attention}consumable{} -> 随机复制{C:attention}1{}张
card in your possession -> 拥有的{C:attention}消耗牌{}
at the end of the {C:attention}shop -> 并给那张牌{C:dark_edition}负片{}效果
```

这些 references 会进入 translator、quality reviewer 和 revision 三个 prompt，作用是约束简中游戏内风格：短句、自然重排英文从句、优先沿用原版表达，避免“从你拥有的牌中随机选择一张，创建其……”这类解释型机器翻译语气。术语强制权威仍然是 locked glossary；TM style references 只作为风格参考。

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
   - 参考按 tier 分层送入 prompt：
     - `locked`：glossary 命中的锁定术语（权威，必须遵循）。
     - `same_context`：dense 命中且 `context_type` 与当前 entry 同类（如同为 `joker_description_line`）。
     - `loose`：其余 dense 命中。
   - prompt 分三段渲染：`Locked glossary:` / `Same-context references:` / `Loose references:`，空段省略。
   - JSONL 的 `rag_refs` 每条带 `context_type` 和 `tier`，保留最终送入 LLM 的参考。

这个设计解决了一个实际问题：Perkeo 描述中同时有 `Negative`、`consumable`、`shop` 等概念。只用整条 entry 做 dense query 时，top-k 容易召回 `consumable/shop`，却漏掉 `Negative -> 负片`。多查询和 glossary 能让每个关键概念都有独立召回机会。分层则让 LLM 区分「必须遵循的锁定术语」和「仅供参考的相似译文」。

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
- 变量 token `#1#` / `#2#` 宽度按 1 处理。
- 不拆 Balatro token。
- 不拆 ASCII 单词，例如 `Sweaty`、`Stake`。
- 尽量不拆 `{C:attention}文本{}` 这种 styled span；宽度只计算内部显示文本，不计算样式 token。
- 尽量不拆中文括号组，例如 `{C:inactive}（必须有空位）{}`。
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
  "apply_mode": "table",
  "apply_warnings": ["text line count mismatch: source=4, target=3"],
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
  "rag_refs": [
    {
      "score": 1.0,
      "mod": "balatro_origin",
      "unit_key": "descriptions.Edition.e_negative.name",
      "context_type": "edition_name",
      "tier": "locked",
      "source": "Negative",
      "target": "负片"
    }
  ],
  "needs_review": false,
  "review": {
    "term_violations": [],
    "consistency_warnings": [],
    "naturalness_warnings": [],
    "meaning_warnings": [],
    "rewrite_hint": "",
    "retry_history": []
  },
  "brief_version": "sha256:..."
}
```

字段含义：

- `ok`: LLM 请求成功，且 token 校验通过。
- `patchable`: 旧字段，表示当前 byte-level patcher 是否可以逐 unit 安全写回。
- `patch_warnings`: 旧字段，不可逐 unit 写回的原因。
- `apply_mode`: 推荐写回策略：
  - `unit`: 默认 apply 可逐 unit 写回。
  - `table`: 中文行数变化，需要 `--table-level` 整块写回。
  - `blocked`: 不能安全写回。
- `apply_warnings`: 写回策略说明。行数变化属于应用策略，不触发 `needs_review`。
- `target_units`: 后续 patch 应该写入的 Lua unit_key。
- `source`: 源英文 entry，用于审查和 diff。
- `rag_refs`: 实际送给 LLM 的翻译记忆引用，每条带 `context_type` 和 `tier`（`locked` / `same_context` / `loose`）。
- `needs_review`: 是否需要人工复审。当前由 token error、锁定术语违规、LLM reviewer 的 naturalness/meaning warning 触发；如果 token/quality 自动重译后通过，则为 `false`。
- `review`: 审查明细。`term_violations` 为锁定术语违规（`kind` 为 `styled` 或 `exact`）；`naturalness_warnings` / `meaning_warnings` 为当前最终译文的 LLM reviewer 警告；`rewrite_hint` 为 reviewer 建议；`retry_history` 记录本 entry 是否因为 token error 或质量 review 自动重译过。
- `brief_version`: 本批使用的 frozen 锁定术语表哈希，用于可复现性审计。模组级 translation brief 的版本记录在 loop `manifest.json` 的 `brief_version` 字段中。

`apply-entry-preview` 有两种写回模式：

- 默认模式只写 `ok=true && needs_review=false && apply_mode=unit`，使用 byte-level patcher，最大限度保留源文件结构。
- `--table-level` 模式还会写入 `ok=true && needs_review=false && apply_mode=table` 的 entry，使用 table-level writer 整段替换对应 `text={...}` / `unlock={...}` 数组。
- `apply_mode=table` 只用于 `descriptions.*` entry；非 `descriptions.*` 的行数变化会保留为 `blocked` / review 项，避免当前 table writer 误处理 `misc.v_text`、`Menus` 等自定义结构。
- `ok=false` 不会写回。
- `needs_review=true` 默认不会写回；只有显式传 `--include-needs-review` 才会写回。
- 旧 preview JSONL 如果没有 `apply_mode`，apply 阶段会从 `patchable`、`patch_warnings` 和目标/译文行数差异推断 `unit` / `table` / `blocked`。

两种模式都会写到新的输出文件，不覆盖 source；写出前会做 patch span diff 校验和 LuaJIT 语法校验。
写回前会统一把 preview 字符串转换为 Lua-safe string content：清理 LLM 偶发生成的内嵌 CR/LF、合并多余空白、转义反斜杠和引号，避免 `"..."` 字符串被真实换行截断。

## 并发设计

`--concurrency` 只控制 LLM 请求并发，不并发写 JSONL。JSONL 始终按源文件 entry 顺序写入。并发验收时重点看控制台日志：

- `LLM queued [...]`: 本 entry 已完成 RAG/style 准备，包含 `refs locked/same_context/loose`、`style_refs`、`credit_lines`。
- `LLM done [...]`: LLM 流程完成，包含 `token_errors`、`needs_review`、`apply_mode`、`term_violations`、`review_warnings`、`quality_retries`、`retry_token_error`。
- `LLM failed [...]`: 本 entry 翻译链路抛异常；JSONL 会写 `ok=false`、`needs_review=true`、`patchable=false`，不会进入默认落地。
- `Preview summary`: 批次级摘要，包含 `ok`、`failed`、`token_error_entries`、`needs_review`、`term_violation_entries`、`quality_retry_entries`、`retry_token_error_entries`、`apply_unit`、`apply_table`、`apply_blocked`。

生成 `zh_CN.lua` 前的硬门槛：

1. preview JSONL 已生成完整目标条目数，`failed=0`。
2. 默认写回建议只接受 `ok=true && needs_review=false && apply_mode=unit`。
3. 如果 `apply_mode=table`，可以加 `--table-level` 写回整段数组；行数变化本身不是质量问题。
4. `needs_review=true` 的条目先人工或再次翻译处理；除非明确接受风险，不加 `--include-needs-review`。
5. `apply-entry-preview` 会先写临时文件并验证 Lua，再替换输出文件；不会覆盖 source 路径。
6. 写回后对任意 mod 运行 `audit-entry-output`，检查 Lua 语法、preview 跳过项、英文残留、未翻译项、同 key 的 description name / misc label 不一致、以及相同英文 name/label 多译；这个审查不依赖具体 mod 的硬编码词。`residual_english` / `untranslated_units` 会带 `severity=rerun|review`，其中 acronym、疑似专名等低置信项只作为 `review` 提示，不默认进入重跑清单。

当前行为：

- RAG 查询在主线程按 entry 顺序执行。
- 每个 LLM 任务创建独立 OpenAI-compatible client。
- LLM 完成日志按真实完成顺序输出。
- JSONL 仍按源 Lua entry 顺序写入。
- 单条失败会写出 `ok=false` / `error`，不会中断整个 preview。

这样既能利用 API 并发，也能保证预览文件顺序稳定，便于审查和后续 patch。

## 闭环翻译流程

真实项目推荐先使用 `translate-entry-loop`，让全量翻译和 rerun 自动连接：

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen python -m app.cli.main translate-entry-loop \
  --repo data/repos/Familiar \
  --source localization/en-us.lua \
  --output localization/zh_CN.lua \
  --work-dir data/artifacts/familiar_entry_translate_loop \
  --limit 9999 \
  --top-k 5 \
  --max-width 18 \
  --concurrency 8 \
  --max-rounds 3
```

每轮固定产物：

```text
round_00_preview.jsonl
round_00_zh_CN.lua
round_00_audit.json
round_00_rerun_keys.txt
round_01_rerun.jsonl
round_01_preview.jsonl
round_01_zh_CN.lua
round_01_audit.json
round_01_rerun_keys.txt
...
manifest.json
mod_translation_brief.json
```

`round_00` 是全量翻译。`round_01+` 使用上一轮 `rerun_keys` 和上一轮 preview 作为 `--context-preview`，只重跑问题 entry，再通过 `merge-entry-preview --safe-updates --apply-consistency` 合并回完整 preview。安全合并只接受 `ok=true && needs_review=false && apply_mode!=blocked` 的 rerun row，避免失败重跑覆盖上一轮可用译文。合并后会对完整 preview 再跑一致性收敛，让重复 source body 复用最佳已接受译文，并把正文/解锁文本中的 rerunnable 残留英文重新标成 `needs_review`。

`mod_translation_brief.json` 是 loop 的默认 brief 状态文件。每轮 audit 后，loop 会把已接受 preview 行中的 name 对照合并进去；下一轮 rerun 会通过 `--brief` 读回这份状态。也可以显式传 `--brief path/to/brief.json` 复用或人工维护某个模组的 brief。

停止条件：

- 当前 audit 不再产生 rerun keys：`stopped_reason=no_rerun_keys`。
- 达到 `--max-rounds`：`stopped_reason=max_rounds`。这种情况说明还有问题需要人工或后续策略处理。

最终 `--output` 会复制最后一轮的 `round_NN_zh_CN.lua`。验收时优先查看：

- `manifest.json`：记录 repo、source、output、work_dir、`brief_path`、`brief_version`、每轮文件和最终 audit summary。
- 最后一轮 `round_NN_audit.json`：看是否还存在 `needs_review`、`severity=rerun` 的 residual/untranslated、label/name mismatch、name inconsistency。
- 最后一轮 `round_NN_rerun_keys.txt`：如果非空，说明达到 `max_rounds` 时仍有待处理 entry。

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
uv run --frozen python -m app.cli.main translate-preview-mod --repo ... --source ... --output ...
uv run --frozen python -m app.cli.main translate-entry-preview-mod --repo ... --source ... --output ... --brief data/artifacts/.../mod_translation_brief.json
uv run --frozen python -m app.cli.main apply-entry-preview --repo ... --source ... --input ... --output localization/zh_CN.lua
uv run --frozen python -m app.cli.main apply-entry-preview --repo ... --source ... --input ... --output localization/zh_CN.lua --table-level
uv run --frozen python -m app.cli.main audit-entry-output --repo ... --source ... --target localization/zh_CN.lua --preview data/artifacts/..._entry_translate_preview.jsonl --json-output data/artifacts/..._entry_translate_audit.json
uv run --frozen python -m app.cli.main audit-rerun-keys --audit data/artifacts/..._entry_translate_audit.json --output data/artifacts/..._rerun_keys.txt
uv run --frozen python -m app.cli.main translate-entry-preview-mod --repo ... --source ... --entry-keys-file data/artifacts/..._rerun_keys.txt --context-preview data/artifacts/..._entry_translate_preview.jsonl --output data/artifacts/..._entry_translate_rerun.jsonl
uv run --frozen python -m app.cli.main merge-entry-preview --base data/artifacts/..._entry_translate_preview.jsonl --updates data/artifacts/..._entry_translate_rerun.jsonl --output data/artifacts/..._entry_translate_preview_merged.jsonl
uv run --frozen python -m app.cli.main merge-entry-preview --base data/artifacts/..._entry_translate_preview.jsonl --updates data/artifacts/..._entry_translate_rerun.jsonl --output data/artifacts/..._entry_translate_preview_merged.jsonl --safe-updates --apply-consistency
uv run --frozen python -m app.cli.main translate-entry-loop --repo ... --source ... --output localization/zh_CN.lua --work-dir data/artifacts/..._entry_translate_loop
uv run --frozen python -m app.cli.main translate-entry-loop --repo ... --source ... --output localization/zh_CN.lua --work-dir data/artifacts/..._entry_translate_loop --brief data/artifacts/..._entry_translate_loop/mod_translation_brief.json
```

术语与质量（Phase 1）：

```bash
uv run --frozen python -m app.cli.main build-style-pack --repo data/repos/Balatro__Origin
uv run --frozen python -m app.cli.main scan-mod-terms --repo ... --source ... --mod-id ...
uv run --frozen python -m app.cli.main check-terms --input data/artifacts/..._entry_translate_preview.jsonl
```

`rag-preview-mod` 仍保留为调试命令，用于单独查看某个模组的 RAG 召回结果，不写 LLM 译文，不作为主翻译路径：

```bash
uv run --frozen python -m app.cli.main rag-preview-mod --repo ... --source ...
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
- table-level Lua writer。
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
- 预构建原版中英风格包。
- 中文 reflow。
- preview `apply_mode` 标记，将质量复审和写回策略分离。
- `apply-entry-preview` 安全子集写回和 `--table-level` 行数变化写回。
- mod-wide name prepass 和全局 name glossary 注入。
- 原版名称模式推断，例如 `Seal -> 蜡封`。
- label-only 条目走 name prepass，避免空 body token error。
- misc extractor 覆盖任意 `misc.<section>` 标量字符串和数组字符串，不只覆盖 `dictionary` / `labels` / `quips`。
- reflow 中 `{...}` 样式 token 宽度为 0，`#1#` / `#2#` 变量宽度为 1。
- Phase 1 质量基础：misc extractor 覆盖、`scan-mod-terms` 候选表、`check-terms` 术语审查、`audit-entry-output` 写回后审查、entry preview 的 `needs_review`/`review`/`brief_version`、RAG 参考分层、官方风格 examples、一次 LLM reviewer 自动重译。
- `translate-entry-loop` 闭环运行：全量 preview、apply、audit、rerun keys、局部 rerun、安全 merge、完整 preview 一致性收敛、再次 apply/audit，产物写入 work-dir 和 `manifest.json`。
- 模组级 translation brief 持久化：loop 默认维护 `<work-dir>/mod_translation_brief.json`，preview 可通过 `--brief` 读取 confirmed name/term，并按 confirmed brief > batch name prepass > context preview > RAG/style refs 的优先级注入上下文。

## 下一步

建议按这个顺序推进：

1. 质量门继续增强
   - 当前 `audit-entry-output` 已能在写回后发现 `null`、`lvl` 等残留英文并生成 rerun keys。
   - preview consistency 已把 `text[]` / `unlock[]` 中的 `severity=rerun` 残留英文前移为 `needs_review`，loop merge 后也会对完整 preview 重跑该检查。
   - 下一步应补全文件级 final reviewer，用于处理 source typo、动态占位异常、短英文专名等需要语义判断的问题。

2. 完整质量评审
   - 当前 entry preview 已有一次 naturalness/meaning reviewer 自动重译。
   - 后续仍需要全文件 final reviewer，检查跨 entry 术语一致性、风格统一和未写回条目。

3. GitHub PR 流程
   - 生成分支。
   - 写入 `zh_CN.lua`。
   - 运行 Lua validator。
   - 创建双语 PR body。
