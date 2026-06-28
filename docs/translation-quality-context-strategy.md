# 翻译质量与模组级上下文策略

更新日期：2026-06-28

本文记录 Fortlatro / Familiar 预览暴露出的质量问题、连续对话上下文方案的可行性分析，以及下一阶段生成 `zh_CN.lua` 前推荐采用的架构。

## 背景

当前流水线已经能做 entry 级 RAG 翻译预览，并能从 preview 写出 `zh_CN.lua`。Fortlatro 与 Familiar 的预览说明：token、JSONL 顺序、table-level 写回、基本术语审查和模组级 brief 持久化已经可控，主要风险转移到了全文件终审、未翻译残留检查和跨 entry 语义一致性。

LLM API 侧也有一个关键事实：OpenAI-compatible chat API 的“对话历史”通常不是服务端自动记忆，而是调用方每次把 `messages` 传给模型。也就是说，是否带历史、带多少历史、历史如何压缩，必须由我们自己的翻译编排层决定。

参考资料：

- OpenAI conversation state: https://platform.openai.com/docs/guides/conversation-state
- OpenAI prompt caching: https://platform.openai.com/docs/guides/prompt-caching
- OpenAI structured outputs: https://platform.openai.com/docs/guides/structured-outputs
- OpenAI text generation / chat messages: https://platform.openai.com/docs/guides/text-generation

## 已确认问题

### 1. 写回后覆盖校验不足

早期 `LuaExtractor` 主要覆盖：

```text
descriptions.<Category>.<entry>.name
descriptions.<Category>.<entry>.text[]
descriptions.<Category>.<entry>.unlock[]
```

Fortlatro 还有：

```text
misc.dictionary.fn_LTMBooster1 = "LTM Pack"
misc.quips.fn_kxtty_quip_3 = { "Negative and negative SHOULD equal positive." }
misc.labels.fn_Mythic = "Mythic"
```

这些现在已经进入 preview 范围：`misc.dictionary`、`misc.labels`、`misc.quips` 都会被提取和分组。仍需补的是写回后全文件覆盖校验：生成 `zh_CN.lua` 后重新 extract，检查是否还有英文残留、缺 key 或 token inventory 变化。

### 2. 名称、标签、描述没有同一个术语状态

同一模组内的名字会同时出现在：

```text
descriptions.Edition.e_fn_Mythic.name
misc.labels.fn_Mythic
main.lua 的 info_queue / apply 文案
其他 description text
```

当前已实现 name prepass 和持久化 mod brief：先翻译本批全部 `name` 字段，生成 mod-wide EN/ZH name glossary，再把它注入每个 entry prompt；`translate-entry-loop` 每轮 audit 后会把已接受的 name 对照写入 `<work-dir>/mod_translation_brief.json`，下一轮和后续批次通过 `--brief` 复用。brief 中的 confirmed name/term 优先级高于当前批次 name prepass、context preview 和 RAG/style refs。

### 3. Dense RAG 仍然会召回噪声

多查询 dense RAG 已经比“整条描述一次检索”更好，但仍有两个缺陷：

- 相似度高不代表翻译片段可直接复用，例如 `card played` 召回了不相关的目标译文。
- `context_type` 还没有在 entry 检索里强约束，同类说明、名称、标签、quips 混在一起时会污染 prompt。

RAG 应该提供“证据”，不能让 LLM 把无关参考当成术语规则。

### 4. 中文自然度和语序仍需二次审查

示例：

```text
{C:attention}+2{}手牌上限当{C:attention}打出{}时
```

token 没坏，但中文语序不自然。当前校验主要检查结构安全，不判断译文是否像中文、是否符合 Balatro 常用表达。

Fortlatro 预览里的 Perkeo 也暴露了同类问题：即使命中了原版条目，如果 prompt 没有明确提供官方中英对照风格，模型仍可能输出“从你拥有的消耗牌中随机选择一张，创建其负片复制牌”这类解释型句式，而不是原版已经采用的“在离开商店时 / 随机复制1张 / 拥有的消耗牌 / 并给那张牌负片效果”。

### 5. 行数变化是写回策略，不是翻译失败

中文 reflow 后行数可能和英文不同，例如源 `text[]` 2 行变成中文 3 行。当前已经将这个状态从质量复审中拆出：

```text
needs_review=false
apply_mode=table
apply_warnings=["text line count mismatch: ..."]
```

默认 apply 只写 `apply_mode=unit`；传 `--table-level` 时会额外写 `apply_mode=table`。行数变化本身不是质量问题。

### 6. Reflow 和清理规则还不够

预览中出现过行首空格、ASCII 词不拆导致局部过长、标点和 token 布局不够自然的问题。当前 reflow 已使用 jieba 和 Balatro 自定义词保护常见术语、styled span 和括号组；样式 token `{...}` 宽度为 0，变量 `#1#` / `#2#` 宽度为 1。reflow 仍只能解决排版，不能替代语言审查。

### 7. 并发翻译和一致性存在天然冲突

当前并发是正确的：RAG 顺序执行，LLM 并发请求，最终 JSONL 按源 entry 顺序写出。但并发 entry 各自独立，无法自然吸收“前面已经决定的译名”。当前通过“批次开始前 name prepass + frozen name glossary + 持久化 mod brief”缓解这个问题；brief 由 loop 在每轮 apply/audit 之后统一 reducer 合并，避免并发任务直接写状态。

## 连续对话历史方案分析

用户提出的思路是：翻译新的句子时，把之前的对话历史也传给 LLM，让整模组翻译更一致。

这个方向有价值，但不适合作为默认主机制。

### 优点

- 小模组、低并发时，模型能看到前文译名和风格。
- 对 quips、梗、主题风格可能有帮助。
- 实现原型简单：把前 N 个 entry 的 source/translation 作为后续 `messages`。

### 风险

- 成本随 entry 数增长，长模组很快浪费 token。
- 前面译错的术语会污染后面所有条目。
- 并发会被迫降到 1，或需要复杂的批次状态合并。
- 重试某个 entry 时，历史状态可能不同，结果不可复现。
- 历史里混入 RAG 噪声后，模型更难分清“参考译文”和“已确认术语”。
- 对写回和审计不友好：很难解释某条译文是受哪个历史片段影响。

### 结论

不要把完整聊天历史作为默认输入。更可靠的方案是“结构化模组级翻译 brief”：把历史压缩成受控状态，只传递确认过的术语、名称、风格规则、禁用译法和少量已确认示例。

完整历史可以作为实验模式，仅用于小模组或人工审查场景。

## 推荐架构

当前实际采用：

```text
独立 entry 翻译
+ 预构建原版 Balatro 风格包
+ 批次内 mod-wide name glossary
+ 确定性术语表
+ RAG 过滤和重排
+ LLM reviewer
+ 可审计的 retry
+ table-level Lua writer
+ 持久化 mod translation brief
```

当前已经补上持久化结构化 mod brief，使批次间能复用已确认译名和术语。

### 1. 原版 Balatro 风格包

原版 `data/repos/Balatro__Origin/localization/en-us.lua` 与 `zh_CN.lua` 是全局风格基准，应该先离线处理成稳定资产，而不是每次翻译时临时抽 10-30 条。

当前实现使用：

```text
app/llm/assets/balatro_origin_style_pack.json
```

生成命令：

```bash
uv run --frozen python -m app.cli.main build-style-pack \
  --repo data/repos/Balatro__Origin \
  --source localization/en-us.lua \
  --target localization/zh_CN.lua \
  --min-per-category 10 \
  --max-per-category 1000
```

风格包按 `descriptions.<Category>` 分桶，当前覆盖 `back`、`blind`、`edition`、`enhanced`、`joker`、`other`、`planet`、`spectral`、`stake`、`tag`、`tarot`、`voucher`，每类至少 10 条。翻译 entry 时只从同类别中选相关样例，并在命中某个官方条目后优先保留该条目的连续文本行，保证模型看到的是完整官方表达，而不是孤立片段。

这个风格包解决的是“怎么像原版简中那样写”的问题；mod brief 解决的是“这个模组内部哪些译名已经确定”的问题。两者不应合并。

### 2. Mod Translation Brief

状态：已落地为模组级 JSON 状态文件。`translate-entry-loop` 默认维护 `<work-dir>/mod_translation_brief.json`，也可以通过 `--brief path/to/brief.json` 指定。`translate-entry-preview-mod --brief` 只读取 brief，不更新；loop 在每轮 `apply-entry-preview` + `audit-entry-output` 后，从已接受 preview row 中合并 confirmed name 对照并保存。当前结构：

```json
{
  "mod_id": "fortlatro",
  "locale": "zh_CN",
  "term_map": {
    "hand size": "手牌上限"
  },
  "name_map": {
    "Seal": "蜡封",
    "Stained Glass": "彩色玻璃"
  },
  "label_map": {},
  "forbidden_terms": {
    "Negative": ["负面", "阴性"]
  },
  "open_questions": [
    {
      "kind": "name_conflict",
      "source": "Speckled",
      "existing": "斑点",
      "candidate": "斑驳",
      "entry_key": "descriptions.Edition.e_fam_speckle",
      "round": 1
    }
  ],
  "proposed_updates": [],
  "last_preview": "data/artifacts/.../round_01_preview.jsonl",
  "last_audit": "data/artifacts/.../round_01_audit.json",
  "updated_at": ""
}
```

它和原始聊天历史的区别：

- brief 是结构化数据，便于审计、diff、人工修改和自动测试。
- brief 只保留“可复用的决策”，不保留完整 prompt 噪声。
- brief 可以在并发批次开始前冻结，保证同一批结果可复现。
- brief 合并只接受 `ok=true && needs_review=false && apply_mode!=blocked` 的 preview row；如果同一英文 name 已有 confirmed 译名，新候选不会覆盖旧值，而是进入 `open_questions`。
- prompt 优先级为：confirmed brief name/term > 当前批次 name prepass / mod-wide name glossary > `--context-preview` 中已接受译名 > locked glossary / same-context RAG / loose RAG / style refs。

### 3. 术语抽取和锁定

翻译前先扫描整个模组：

```text
descriptions.*.*.name
misc.labels.*
styled span 中的英文术语
main.lua 中 info_queue / apply 文案里出现的本地化 key
```

生成候选术语表，再按优先级合并：

```text
人工锁定术语 > 原版 Balatro TM > 同模组 labels/name 一致性 > dense RAG 建议 > LLM 猜测
```

LLM 可以建议译名，但不能覆盖人工锁定和原版术语。

### 4. RAG 从“相似句子”升级为“分层证据”

prompt 中应分成几类，而不是简单列表：

```text
Locked glossary:
- Negative => 负片

Same-context references:
- EN: +#1# hand size
  ZH: 手牌上限+#1#

Loose references:
- EN: ...
  ZH: ...
```

检索策略：

- `name` 查 name/label 记忆，不混 description line。
- `description_line` 优先查同 context_type。
- `quips` 单独检索 quip/短句，不混规则说明。
- 对高分但目标明显不对应的条目做 rerank 或 reviewer 过滤。

### 5. Entry Translator 继续独立调用，但输入 brief

每个 entry 请求包含：

```text
system rules
Balatro style references: official examples first, same-category translated TM for custom categories
frozen mod brief
当前 entry source
分层 RAG references
严格 JSON schema
```

默认仍允许 `LLM_CONCURRENCY > 1`。同一批 entry 使用同一个 frozen brief，输出完成后再进入 reviewer 和 brief update 阶段。

### 6. Reviewer 和自动重试

新增审查步骤，不直接信任 translator：

```text
token_inventory_ok
term_map_compliance
name_label_consistency
source_meaning_coverage
naturalness_score
line_width_warnings
patchability
```

如果失败：

```text
retry_count < N -> 带 reviewer 反馈重译
retry_count >= N -> 标记 needs_review，不写回
```

这一步能解决“token 没坏但中文很怪”的问题。

### 7. Lua 写回策略

当前已实现 `apply-entry-preview` 和 table-level writer：

```text
读取源 Lua AST
替换 name 字符串
替换 text/unlock table 的字符串数组
允许 text/unlock 行数变化
写出 zh_CN.lua
LuaJIT 编译校验
```

默认 `apply-entry-preview` 仍保留 byte-level patcher 作为 `apply_mode=unit` 的快速路径；传 `--table-level` 时，会对 `apply_mode=table` 的 row 使用 table-level writer。`patchable` / `patch_warnings` 作为旧字段继续保留，便于兼容旧 JSONL。后续还应补写回后的 extractor 覆盖校验和 token inventory 复查。

## 当前数据契约

### Preview Row

当前 JSONL 已包含：

```json
{
  "entry_key": "descriptions.Edition.e_fn_Mythic",
  "ok": true,
  "needs_review": false,
  "apply_mode": "table",
  "apply_warnings": ["text line count mismatch: source=2, target=3"],
  "review": {
    "term_violations": [],
    "consistency_warnings": [],
    "naturalness_warnings": [],
    "meaning_warnings": []
  },
  "brief_version": "sha256:...",
  "context_refs": {
    "locked_terms": [],
    "same_context_refs": [],
    "loose_refs": []
  }
}
```

这里的 `brief_version` 仍是本批 frozen locked term map 的哈希，用于术语审计兼容。模组级 translation brief 的版本由 `translate-entry-loop` 写入 `manifest.json` 的 `brief_version` 字段，和 `brief_path` 一起记录。

### Brief 更新规则

不要让每个并发任务直接写 brief。采用批次合并：

```text
1. 冻结 brief_v1。
2. 并发翻译 batch。
3. apply/audit 产生已接受 preview row 和问题清单。
4. reducer 按源顺序合并已接受 name 对照，生成 brief_v2；冲突进入 open_questions。
5. 下一批使用 brief_v2。
```

这样既保留一致性，又不会出现并发竞态。

## 分阶段落地计划

### Phase 1：先堵住质量漏洞

> 状态：已落地（2026-06-27）。下述质量基础均已实现并接入 entry preview。

- 扩展 extractor，覆盖 `misc.dictionary`、`misc.labels`、`misc.quips`。
- 生成 mod-level name/label 候选表。
- 增加术语一致性检查，至少覆盖 exact term 和 styled term。
- RAG prompt 分层：locked glossary、same-context refs、loose refs。
- JSONL 增加 `needs_review`、`review`、`brief_version`。
- 增加 entry 级 LLM reviewer；发现中文语序生硬或明显语义偏移时，带反馈自动重译一次。
- 增加批次内 name prepass 和全局 name glossary。
- 增加原版名称模式推断，例如 `Seal -> 蜡封`。

落地说明：

- `app/lua/extractor.py` 新增 `_extract_misc_units` / `_field_key`，misc 单元走行级预览路径，entry 级流程自动过滤。
- `app/rag/mod_terms.py` + CLI `scan-mod-terms` 产出候选表。
- `app/rag/term_checker.py` + CLI `check-terms` 做锁定术语审查（styled + context-aware exact，跳过 identity 映射）。
- `app/llm/translator.py` 的 `TranslationReference` 加 `tier`，prompt 分三段渲染。
- entry preview 每批冻结 `build_locked_term_map` 并哈希为 `brief_version`，同时保留 locked term 的 context metadata，违规进 `review.term_violations`。
- `app/llm/translator.py` 增加 entry quality reviewer 和 revision prompt；初次 token mismatch 和 quality review 都可触发一次 revision，`review.retry_history` 记录自动重译原因。
- name prepass 生成批次内全局 name glossary，并注入每个 entry prompt；相同英文 name 出现多译时优先采用 description entry 译名，回填 label-only 条目。
- 原版名称模式可推断复合词后缀，例如 `Seal -> 蜡封`；非原版跨类别精确同名引用和单词级误导引用会在 name prepass 中过滤，类别由 `descriptions.<Category>` 动态推导，不依赖特定 mod。
- label-only 条目直接使用 name prepass 结果，不再调用 entry translator 生成空 body。
- 更细的人工术语审批和全文件 final reviewer 仍属 Phase 3-4。

### Phase 2：解决写回限制

> 状态：主体已落地（2026-06-27）。`apply-entry-preview` 已可输出 `zh_CN.lua`，`--table-level` 支持 text/unlock 行数变化，并在写出前跑 LuaJIT compile check。行数变化通过 `apply_mode=table` 表示，不再触发 `needs_review`。

- 已实现 table-level Lua writer。
- 已支持 text/unlock 行数变化。
- 已写出 `zh_CN.lua` 后跑 LuaJIT compile check。
- 待增强：写回后重新 extract，确认 key 覆盖和 token inventory。

### Phase 3：模组级上下文闭环

> 状态：主体已落地（2026-06-28）。命令级 loop、preview 一致性收敛和 JSON brief 持久化已经接入；`proposed_updates` 和更细的人工术语审批仍可后续增强。

- `translate-entry-loop` 已提供命令级闭环：全量 preview、apply、audit、rerun keys、局部 rerun、安全 merge、完整 preview 一致性收敛、再次 apply/audit，并把每轮产物写入 work-dir/manifest，方便人工验收和后续分析。
- preview consistency 已能复用同类别内重复 source body 的最佳译文，并把 `text[]` / `unlock[]` 中的 rerunnable 残留英文前移为 `needs_review`；rerun merge 后也会对完整 preview 再跑一次，减少局部 rerun 后旧行继续污染最终 apply。
- `translate-entry-loop` 默认维护 `<work-dir>/mod_translation_brief.json`；也可显式传 `--brief`。
- `translate-entry-preview-mod --brief` 会把 confirmed brief name/term 作为 frozen context 注入 prompt。
- brief reducer 在每轮 apply/audit 后合并已接受 preview row，下一轮继续使用更新后的 brief。
- `manifest.json` 记录 `brief_path` 和 `brief_version`。
- 待增强：翻译前预扫描整模组生成更多候选 term、reviewer 输出 `proposed_updates`、人工审批后再提升为 confirmed term/name。

### Phase 4：完整模组评审

- 全文件翻译后跑 final reviewer。
- 检查 name/label/text/quips 一致性。
- 输出人工可看的 summary：
  - 已锁定术语
  - 存疑译名
  - 未写回条目
  - reviewer 警告
- 再进入 PR 生成流程。

## 推荐默认模式

```text
context_mode=brief
concurrency=4
batch_size=20
max_width=18
strict_terms=true
reviewer=true
write_mode=table
```

当前已可安全用 `--concurrency > 1` 验收并发链路；为了最高质量，仍建议先用较低并发审查首批结果，再根据 API 稳定性提高。

实验模式：

```text
context_mode=sequential_history
concurrency=1
history_limit=10
```

`sequential_history` 只用于对比实验，不作为默认。评估指标包括术语一致性、自然度、token 成本、失败重试稳定性和最终 reviewer 通过率。

## 下一步建议

最靠谱的顺序是：

1. 继续增强写回后的 extractor 覆盖校验、token inventory 复查和英文残留扫描。
2. 做全文件 final reviewer，覆盖跨 entry 术语、source typo、短英文专名和动态占位异常。
3. 给 mod brief 增加人工审批流程，把 `open_questions` / `proposed_updates` 明确提升为 confirmed name/term。
4. 最后再实验连续对话历史。

原因是：连续历史只能改善“风格记忆”，不能修复漏抽取、RAG 噪声、写回行数和术语锁定这些基础问题。基础状态先结构化，后续无论用并发、顺序还是混合批次，都会更稳。
