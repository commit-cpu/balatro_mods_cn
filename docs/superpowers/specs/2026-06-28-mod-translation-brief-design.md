# Mod Translation Brief Design

## Goal

Persist mod-level translation decisions so repeated runs and concurrent entry translation reuse confirmed names, labels, terms, and review decisions instead of rediscovering them from scratch.

## Context

The current workflow can translate a full mod with `translate-entry-loop`, apply the preview, audit the generated Lua, rerun problematic entries, safely merge rerun results, and audit again. That makes the pipeline usable, but the state that stabilizes a mod's terminology still lives inside one run:

- name prepass builds a batch-local EN/ZH glossary
- `--context-preview` seeds reruns from a previous preview
- audit finds inconsistencies after apply
- loop artifacts preserve evidence, but not a reusable mod brief

The next step is a persistent, reviewable `mod_translation_brief.json` that can be loaded before translation and updated after each loop round.

## Chosen Approach

Use a JSON brief file first, not SQLite.

Reasons:

- It is easy to inspect and manually edit during real mod validation.
- It is easy to diff in git or compare across loop runs.
- The schema can evolve while the project is still learning from real mods.
- It avoids adding DB migrations before the state model is stable.

SQLite can be added later after the JSON contract proves useful.

## File Location

Default path:

```text
<work-dir>/mod_translation_brief.json
```

For example:

```text
data/artifacts/familiar_entry_translate_loop/mod_translation_brief.json
```

CLI commands should also accept an explicit path:

```bash
--brief data/artifacts/familiar_entry_translate_loop/mod_translation_brief.json
```

If no `--brief` is passed, `translate-entry-loop` uses the default path under its resolved work dir. `translate-entry-preview-mod` may also accept `--brief`, but it should not create/update the brief by itself; it only reads the frozen brief.

## Schema

Initial schema:

```json
{
  "schema_version": 1,
  "mod_id": "Familiar",
  "locale": "zh_CN",
  "source": {
    "repo": "data/repos/Familiar",
    "source": "localization/en-us.lua"
  },
  "name_map": {
    "Seal": "蜡封"
  },
  "label_map": {},
  "term_map": {},
  "forbidden_terms": {},
  "open_questions": [],
  "proposed_updates": [],
  "last_preview": "",
  "last_audit": "",
  "updated_at": "2026-06-28T00:00:00Z"
}
```

Field meanings:

- `schema_version`: integer schema gate. Unknown future versions should fail clearly.
- `mod_id`: display/repo-derived mod id for traceability.
- `locale`: currently `zh_CN`.
- `source`: repo/source path that produced the brief.
- `name_map`: confirmed source name to target name mappings.
- `label_map`: confirmed misc label mappings when label-only entries are known.
- `term_map`: confirmed non-name terms local to this mod.
- `forbidden_terms`: source term to rejected target translations.
- `open_questions`: conflicts or uncertain decisions requiring human review.
- `proposed_updates`: lower-confidence suggestions that were not promoted.
- `last_preview`: most recent preview path that contributed to this brief.
- `last_audit`: most recent audit path that contributed to this brief.
- `updated_at`: ISO timestamp for auditability.

## Loading Rules

When a brief exists:

1. Load it before name prepass.
2. Validate `schema_version == 1`.
3. Use `name_map` as confirmed seeds for matching source names.
4. Use confirmed seeds at higher priority than RAG, TM, context preview, or LLM guesses.
5. Do not let name prepass overwrite a confirmed brief mapping.
6. Include confirmed brief mappings in the prompt as a separate section before context preview examples.

If brief and context preview disagree, brief wins.

## Updating Rules

`translate-entry-loop` updates the brief after each apply/audit round.

Promotion rules:

- Only consider preview rows with `ok=true` and `needs_review!=true`.
- Only consider rows with string `source.name` and string `name`.
- Ignore rows whose `apply_mode` is `blocked`.
- Ignore names that audit classifies as review-only acronyms/proper names unless they already exist in the brief.
- If a source name has no existing mapping, add it to `name_map`.
- If the existing mapping is identical, keep it unchanged.
- If the existing mapping differs, do not overwrite; add an `open_questions` item.

Initial `open_questions` item shape:

```json
{
  "kind": "name_conflict",
  "source": "Speckled",
  "existing": "斑点",
  "candidate": "斑纹",
  "entry_key": "descriptions.Edition.e_fam_speckle",
  "round": 2
}
```

The reducer must dedupe identical open questions so repeated loop rounds do not spam the brief.

## Prompt Integration

Add a brief context renderer that produces compact text like:

```text
Confirmed mod translation brief:
- Seal => 蜡封
- Speckled => 斑点
```

This section should be joined before:

- mod-wide name glossary generated in the current batch
- context preview accepted examples

This order makes the hierarchy explicit:

```text
brief confirmed terms > current batch name prepass > accepted previous preview examples > RAG/style references
```

## CLI Changes

`translate-entry-preview-mod`:

- Add `--brief PATH`.
- Load brief if present.
- Apply brief seeds before `_translate_mod_entry_names`.
- Include brief context in `name_context`.
- Keep preview rows' existing `brief_version`; later work may expand this hash to include brief content.

`translate-entry-loop`:

- Add `--brief PATH`.
- Resolve default to `<work-dir>/mod_translation_brief.json`.
- Pass the brief to every preview/rerun call.
- Update the brief after each audit using the merged/full preview for that round.
- Write `brief_path` and `brief_version` into `manifest.json`.

Optional utility commands can be added later, but are not required for the first implementation.

## Error Handling

- Missing brief path is not an error; create it when the loop first has accepted rows.
- Invalid JSON is a hard error with the path in the message.
- Unsupported schema version is a hard error.
- Conflicts are not hard errors; they become `open_questions`.
- Brief write should be atomic: write a temp file in the same directory, then replace.

## Testing Strategy

Add focused unit tests for a new brief module:

- default path generation
- load missing file returns an empty brief
- unsupported schema version fails
- brief version changes when content changes
- confirmed name seeds override context preview/prepass guesses
- reducer promotes accepted names
- reducer records conflicts without overwriting
- reducer dedupes open questions

Add CLI tests:

- `translate-entry-preview-mod --brief` passes confirmed names into name prepass and prompt context.
- `translate-entry-loop` passes the same brief path through full and rerun rounds.
- `translate-entry-loop` writes/updates the default brief and records it in manifest.

## Out of Scope

- SQLite persistence for brief data.
- Full final reviewer.
- Manual brief editing UI.
- Automatic PR generation.
- Semantic correction of source typos such as `Consumble` or dynamic anomalies such as `null`.

Those remain follow-up phases after the persistent brief is integrated.
