# Mod Translation Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent JSON mod translation briefs and connect them to entry translation and the closed translation loop.

**Architecture:** Create a focused `app/cli/translation_brief.py` module for JSON schema, loading, rendering, versioning, and reducer updates. `translate-entry-preview-mod` reads a frozen brief and uses it as the highest-priority name seed/prompt context. `translate-entry-loop` owns brief path resolution, passes the same brief to every preview/rerun, updates the brief after each round, and records brief metadata in the manifest.

**Tech Stack:** Python 3.12, Typer CLI, pytest, JSON files, existing preview JSONL rows and audit JSON reports.

---

## File Structure

- Create `app/cli/translation_brief.py`: JSON brief dataclass/helpers, atomic read/write, version hash, prompt rendering, reducer update logic.
- Create `tests/test_translation_brief.py`: unit tests for brief behavior.
- Modify `app/cli/main.py`: add `--brief` to preview and loop commands, seed name prepass, render prompt context, update brief after each loop round.
- Modify `app/cli/translation_loop.py`: add default brief path and manifest support.
- Modify `tests/test_cli.py`: CLI integration tests for preview and loop brief behavior.
- Modify `tests/test_translation_loop.py`: default path/manifest metadata tests.
- Modify `docs/current-translation-pipeline.md` and `docs/translation-quality-context-strategy.md`: document brief usage and artifact paths.

## Task 1: Brief Module Skeleton and Serialization

**Files:**
- Create: `app/cli/translation_brief.py`
- Create: `tests/test_translation_brief.py`

- [ ] **Step 1: Write failing tests for empty/default brief behavior**

Add to `tests/test_translation_brief.py`:

```python
from pathlib import Path

import pytest

from app.cli.translation_brief import (
    TranslationBrief,
    brief_version,
    default_brief_path,
    load_translation_brief,
    save_translation_brief,
)


def test_default_brief_path_lives_under_work_dir(tmp_path: Path) -> None:
    assert default_brief_path(tmp_path / "loop") == tmp_path / "loop" / "mod_translation_brief.json"


def test_load_missing_brief_returns_empty_brief(tmp_path: Path) -> None:
    brief = load_translation_brief(
        tmp_path / "missing.json",
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )

    assert brief == TranslationBrief(
        schema_version=1,
        mod_id="Familiar",
        locale="zh_CN",
        source={"repo": "data/repos/Familiar", "source": "localization/en-us.lua"},
        name_map={},
        label_map={},
        term_map={},
        forbidden_terms={},
        open_questions=[],
        proposed_updates=[],
        last_preview="",
        last_audit="",
        updated_at="",
    )


def test_save_and_load_brief_round_trips_json(tmp_path: Path) -> None:
    path = tmp_path / "brief.json"
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"

    save_translation_brief(path, brief)
    loaded = load_translation_brief(
        path,
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )

    assert loaded.name_map == {"Seal": "蜡封"}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_brief_version_changes_when_content_changes(tmp_path: Path) -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    first = brief_version(brief)
    brief.name_map["Seal"] = "蜡封"
    second = brief_version(brief)

    assert first.startswith("sha256:")
    assert second.startswith("sha256:")
    assert first != second
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_brief.py -q
```

Expected: import failure because `app.cli.translation_brief` does not exist.

- [ ] **Step 3: Implement minimal brief module**

Create `app/cli/translation_brief.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any


BRIEF_SCHEMA_VERSION = 1
BRIEF_LOCALE = "zh_CN"
BRIEF_FILENAME = "mod_translation_brief.json"


@dataclass
class TranslationBrief:
    schema_version: int
    mod_id: str
    locale: str
    source: dict[str, str]
    name_map: dict[str, str] = field(default_factory=dict)
    label_map: dict[str, str] = field(default_factory=dict)
    term_map: dict[str, str] = field(default_factory=dict)
    forbidden_terms: dict[str, list[str]] = field(default_factory=dict)
    open_questions: list[dict[str, Any]] = field(default_factory=list)
    proposed_updates: list[dict[str, Any]] = field(default_factory=list)
    last_preview: str = ""
    last_audit: str = ""
    updated_at: str = ""

    @classmethod
    def empty(cls, *, mod_id: str, repo: Path, source: str) -> "TranslationBrief":
        return cls(
            schema_version=BRIEF_SCHEMA_VERSION,
            mod_id=mod_id,
            locale=BRIEF_LOCALE,
            source={"repo": str(repo), "source": source},
        )


def default_brief_path(work_dir: Path) -> Path:
    return work_dir / BRIEF_FILENAME


def load_translation_brief(path: Path, *, mod_id: str, repo: Path, source: str) -> TranslationBrief:
    if not path.exists():
        return TranslationBrief.empty(mod_id=mod_id, repo=repo, source=source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"translation brief must be a JSON object: {path}")
    version = payload.get("schema_version")
    if version != BRIEF_SCHEMA_VERSION:
        raise ValueError(f"unsupported translation brief schema_version={version!r}: {path}")
    brief = TranslationBrief.empty(mod_id=mod_id, repo=repo, source=source)
    for key in asdict(brief):
        if key in payload:
            setattr(brief, key, payload[key])
    _normalize_brief(brief)
    return brief


def save_translation_brief(path: Path, brief: TranslationBrief) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(brief), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def brief_version(brief: TranslationBrief) -> str:
    payload = json.dumps(asdict(brief), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_brief(brief: TranslationBrief) -> None:
    if not isinstance(brief.name_map, dict):
        brief.name_map = {}
    if not isinstance(brief.label_map, dict):
        brief.label_map = {}
    if not isinstance(brief.term_map, dict):
        brief.term_map = {}
    if not isinstance(brief.forbidden_terms, dict):
        brief.forbidden_terms = {}
    if not isinstance(brief.open_questions, list):
        brief.open_questions = []
    if not isinstance(brief.proposed_updates, list):
        brief.proposed_updates = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_brief.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/cli/translation_brief.py tests/test_translation_brief.py
git commit -m "Add translation brief persistence"
```

## Task 2: Brief Rendering, Seeds, and Reducer

**Files:**
- Modify: `app/cli/translation_brief.py`
- Modify: `tests/test_translation_brief.py`

- [ ] **Step 1: Write failing tests for prompt rendering and reducer behavior**

Append to `tests/test_translation_brief.py`:

```python
from app.cli.translation_brief import (
    apply_brief_name_seeds,
    render_brief_context,
    update_brief_from_preview,
)


def test_apply_brief_name_seeds_overrides_existing_seed() -> None:
    seeds = {"descriptions.Edition.e_seal": "封印"}
    source_names = {"descriptions.Edition.e_seal": "Seal"}
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"

    apply_brief_name_seeds(seeds, source_names, brief)

    assert seeds == {"descriptions.Edition.e_seal": "蜡封"}


def test_render_brief_context_lists_confirmed_names_and_terms() -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Seal"] = "蜡封"
    brief.term_map["hand size"] = "手牌上限"

    assert render_brief_context(brief) == (
        "Confirmed mod translation brief:\n"
        "- Seal => 蜡封\n"
        "- hand size => 手牌上限"
    )


def test_update_brief_from_preview_promotes_accepted_names(tmp_path: Path) -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    rows = [
        {
            "entry_key": "descriptions.Edition.e_seal",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "蜡封",
            "source": {"name": "Seal"},
        }
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=0,
    )

    assert brief.name_map == {"Seal": "蜡封"}
    assert brief.last_preview == str(tmp_path / "preview.jsonl")
    assert brief.last_audit == str(tmp_path / "audit.json")


def test_update_brief_from_preview_records_conflict_without_overwrite(tmp_path: Path) -> None:
    brief = TranslationBrief.empty(
        mod_id="Familiar",
        repo=Path("data/repos/Familiar"),
        source="localization/en-us.lua",
    )
    brief.name_map["Speckled"] = "斑点"
    rows = [
        {
            "entry_key": "descriptions.Edition.e_speckle",
            "ok": True,
            "needs_review": False,
            "apply_mode": "unit",
            "name": "斑纹",
            "source": {"name": "Speckled"},
        }
    ]

    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=2,
    )
    update_brief_from_preview(
        brief,
        rows,
        audit_report={"untranslated_units": [], "residual_english": []},
        preview_path=tmp_path / "preview.jsonl",
        audit_path=tmp_path / "audit.json",
        round_index=2,
    )

    assert brief.name_map["Speckled"] == "斑点"
    assert brief.open_questions == [
        {
            "kind": "name_conflict",
            "source": "Speckled",
            "existing": "斑点",
            "candidate": "斑纹",
            "entry_key": "descriptions.Edition.e_speckle",
            "round": 2,
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_brief.py -q
```

Expected: import failures for missing helper functions.

- [ ] **Step 3: Implement renderer, seed application, and reducer**

Add to `app/cli/translation_brief.py`:

```python
def render_brief_context(brief: TranslationBrief) -> str:
    lines = ["Confirmed mod translation brief:"]
    for source, target in sorted(brief.name_map.items()):
        if source and target:
            lines.append(f"- {source} => {target}")
    for source, target in sorted(brief.term_map.items()):
        if source and target:
            lines.append(f"- {source} => {target}")
    return "\n".join(lines) if len(lines) > 1 else ""


def apply_brief_name_seeds(
    seeds: dict[str, str],
    source_names_by_entry: dict[str, str],
    brief: TranslationBrief,
) -> None:
    for entry_key, source_name in source_names_by_entry.items():
        target_name = brief.name_map.get(source_name)
        if isinstance(target_name, str) and target_name:
            seeds[entry_key] = target_name


def update_brief_from_preview(
    brief: TranslationBrief,
    rows: list[dict[str, object]],
    *,
    audit_report: dict[str, object],
    preview_path: Path,
    audit_path: Path,
    round_index: int,
) -> None:
    review_only_names = _review_only_name_texts(audit_report)
    for row in rows:
        if row.get("ok") is not True or row.get("needs_review") is True:
            continue
        if row.get("apply_mode") == "blocked":
            continue
        source = row.get("source")
        if not isinstance(source, dict):
            continue
        source_name = source.get("name")
        target_name = row.get("name")
        entry_key = row.get("entry_key")
        if not isinstance(source_name, str) or not isinstance(target_name, str):
            continue
        if not source_name or not target_name:
            continue
        if source_name in review_only_names and source_name not in brief.name_map:
            continue
        existing = brief.name_map.get(source_name)
        if existing is None:
            brief.name_map[source_name] = target_name
        elif existing != target_name:
            _append_open_question(
                brief,
                {
                    "kind": "name_conflict",
                    "source": source_name,
                    "existing": existing,
                    "candidate": target_name,
                    "entry_key": entry_key if isinstance(entry_key, str) else "",
                    "round": round_index,
                },
            )
    brief.last_preview = str(preview_path)
    brief.last_audit = str(audit_path)


def _review_only_name_texts(audit_report: dict[str, object]) -> set[str]:
    values: set[str] = set()
    for section in ("residual_english", "untranslated_units"):
        items = audit_report.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("severity") != "review":
                continue
            unit_key = item.get("unit_key")
            text = item.get("text")
            if isinstance(unit_key, str) and unit_key.endswith(".name") and isinstance(text, str):
                values.add(text)
    return values


def _append_open_question(brief: TranslationBrief, question: dict[str, Any]) -> None:
    if question not in brief.open_questions:
        brief.open_questions.append(question)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_brief.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/cli/translation_brief.py tests/test_translation_brief.py
git commit -m "Add translation brief reducer"
```

## Task 3: Connect Brief to Entry Preview

**Files:**
- Modify: `app/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI test for `translate-entry-preview-mod --brief`**

Add a test near the existing context preview/name prepass tests in `tests/test_cli.py`:

```python
def test_translate_entry_preview_mod_uses_brief_name_seed(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "Mod"
    source = repo / "localization" / "en-us.lua"
    source.parent.mkdir(parents=True)
    source.write_text(
        "return { descriptions = { Edition = { e_seal = { name = 'Seal', text = { 'Seal Card' } } } } }\n",
        encoding="utf-8",
    )
    output = tmp_path / "preview.jsonl"
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mod_id": "Mod",
                "locale": "zh_CN",
                "source": {"repo": str(repo), "source": "localization/en-us.lua"},
                "name_map": {"Seal": "蜡封"},
                "label_map": {},
                "term_map": {},
                "forbidden_terms": {},
                "open_questions": [],
                "proposed_updates": [],
                "last_preview": "",
                "last_audit": "",
                "updated_at": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr("app.cli.main.load_settings", lambda: fake_settings(tmp_path))
    monkeypatch.setattr("app.cli.main.QdrantStore", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.cli.main.build_locked_term_map", lambda db_path: {})
    monkeypatch.setattr("app.cli.main.build_locked_term_info", lambda db_path: {})
    monkeypatch.setattr("app.cli.main.retrieve_entry_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main.retrieve_glossary_references", lambda **kwargs: [])
    monkeypatch.setattr("app.cli.main._llm_client", lambda: object())
    monkeypatch.setattr("app.cli.main.load_style_pack", lambda path=None: object())
    monkeypatch.setattr("app.cli.main.select_style_examples", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.cli.main.select_tm_style_examples", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "app.cli.main._translate_mod_entry_names",
        lambda *args, seed_names=None, **kwargs: (dict(seed_names or {}), []),
    )

    class FakeTranslator:
        def __init__(self, client):
            pass

        def translate_entry(self, item, **kwargs):
            captured["pretranslated_name"] = kwargs.get("pretranslated_name")
            captured["name_context"] = kwargs.get("name_context")

            class Result:
                name = "蜡封"
                text = ["蜡封牌"]
                unlock = []
                token_errors = []

            return Result()

        def review_entry_translation(self, *args, **kwargs):
            class Review:
                term_violations = []
                consistency_warnings = []
                naturalness_warnings = []
                meaning_warnings = []
                rewrite_hint = ""

            return Review()

    monkeypatch.setattr("app.cli.main.Translator", FakeTranslator)

    result = CliRunner().invoke(
        app,
        [
            "translate-entry-preview-mod",
            "--repo",
            str(repo),
            "--source",
            "localization/en-us.lua",
            "--output",
            str(output),
            "--brief",
            str(brief),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["pretranslated_name"] == "蜡封"
    assert "Confirmed mod translation brief" in captured["name_context"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_cli.py::test_translate_entry_preview_mod_uses_brief_name_seed -q
```

Expected: CLI rejects `--brief`.

- [ ] **Step 3: Implement preview brief loading and prompt integration**

Modify imports in `app/cli/main.py` to include:

```python
from app.cli.translation_brief import (
    TranslationBrief,
    apply_brief_name_seeds,
    load_translation_brief,
    render_brief_context,
)
```

Modify `translate_entry_preview_mod` signature:

```python
brief: Path | None = typer.Option(None, exists=False, dir_okay=False),
```

After `work_items` are built and `context_rows` are read:

```python
translation_brief = (
    load_translation_brief(brief, mod_id=repo.name, repo=repo, source=source)
    if brief is not None
    else TranslationBrief.empty(mod_id=repo.name, repo=repo, source=source)
)
source_names_by_entry = {
    item.entry.entry_key: item.entry.name.source_text
    for item in work_items
    if item.entry.name is not None
}
seeded_names = _seed_pretranslated_names(work_items, context_rows)
apply_brief_name_seeds(seeded_names, source_names_by_entry, translation_brief)
```

Join brief context before current contexts:

```python
name_context = _join_prompt_contexts(
    render_brief_context(translation_brief),
    _render_mod_name_glossary(work_items, pretranslated_names),
    _render_preview_translation_context(context_rows),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_cli.py::test_translate_entry_preview_mod_uses_brief_name_seed -q
```

Expected: test passes.

- [ ] **Step 5: Commit**

```bash
git add app/cli/main.py tests/test_cli.py
git commit -m "Use translation brief in entry preview"
```

## Task 4: Connect Brief to Translation Loop and Manifest

**Files:**
- Modify: `app/cli/main.py`
- Modify: `app/cli/translation_loop.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_translation_loop.py`

- [ ] **Step 1: Write failing tests for loop brief path and manifest**

Add to `tests/test_translation_loop.py`:

```python
from app.cli.translation_loop import default_loop_brief_path


def test_default_loop_brief_path_lives_under_work_dir(tmp_path) -> None:
    assert default_loop_brief_path(tmp_path / "loop") == tmp_path / "loop" / "mod_translation_brief.json"
```

Update `test_write_loop_manifest_records_round_files_and_final_summary` to pass:

```python
brief_path=work_dir / "mod_translation_brief.json",
brief_version="sha256:abc",
```

and assert:

```python
assert payload["brief_path"] == str(work_dir / "mod_translation_brief.json")
assert payload["brief_version"] == "sha256:abc"
```

Update `tests/test_cli.py::test_translate_entry_loop_runs_full_then_rerun_until_clean`:

- make `fake_translate_entry_preview_mod` assert `kwargs["brief"] == work_dir / "mod_translation_brief.json"`
- make fake preview rows include `source.name` and `name`
- after command, assert the brief file exists and has a `name_map`
- assert manifest includes `brief_path` and `brief_version`

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_loop.py tests/test_cli.py::test_translate_entry_loop_runs_full_then_rerun_until_clean -q
```

Expected: missing `default_loop_brief_path`, missing manifest parameters, and missing `brief` kwarg.

- [ ] **Step 3: Implement loop brief path, pass-through, update, and manifest metadata**

In `app/cli/translation_loop.py`:

```python
from app.cli.translation_brief import default_brief_path


def default_loop_brief_path(work_dir: Path) -> Path:
    return default_brief_path(work_dir)
```

Extend `write_loop_manifest` signature with:

```python
brief_path: Path | None = None,
brief_version: str = "",
```

and include in payload:

```python
"brief_path": str(brief_path) if brief_path is not None else "",
"brief_version": brief_version,
```

In `app/cli/main.py`, import:

```python
from app.cli.translation_brief import (
    brief_version as translation_brief_version,
    default_brief_path,
    save_translation_brief,
    update_brief_from_preview,
)
```

Add `brief: Path | None = typer.Option(None, exists=False, dir_okay=False)` to `translate_entry_loop`.

Resolve:

```python
resolved_brief_path = brief or default_brief_path(resolved_work_dir)
translation_brief = load_translation_brief(
    resolved_brief_path,
    mod_id=repo.name,
    repo=repo,
    source=source,
)
```

Pass `brief=resolved_brief_path` into every `translate_entry_preview_mod` call.

After audit report is read:

```python
preview_rows = _read_preview_rows(artifacts.preview)
update_brief_from_preview(
    translation_brief,
    preview_rows,
    audit_report=report,
    preview_path=artifacts.preview,
    audit_path=artifacts.audit,
    round_index=round_index,
)
save_translation_brief(resolved_brief_path, translation_brief)
current_brief_version = translation_brief_version(translation_brief)
```

Pass `brief_path=resolved_brief_path` and `brief_version=current_brief_version` to every manifest write.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/test_translation_loop.py tests/test_cli.py::test_translate_entry_loop_runs_full_then_rerun_until_clean -q
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/cli/main.py app/cli/translation_loop.py tests/test_cli.py tests/test_translation_loop.py
git commit -m "Update translation loop brief state"
```

## Task 5: Documentation and Full Verification

**Files:**
- Modify: `docs/current-translation-pipeline.md`
- Modify: `docs/translation-quality-context-strategy.md`

- [ ] **Step 1: Update docs**

Document:

- default brief artifact path
- `--brief` on preview/loop commands
- brief priority over context preview
- brief update behavior after each loop round
- manifest `brief_path` / `brief_version`

- [ ] **Step 2: Run full verification**

Run:

```bash
UV_CACHE_DIR=.cache/uv uv run --frozen pytest -q
UV_CACHE_DIR=.cache/uv uv run --frozen ruff check .
git diff --check
```

Expected:

- `pytest`: all tests pass
- `ruff`: `All checks passed!`
- `git diff --check`: no output, exit 0

- [ ] **Step 3: Commit**

```bash
git add docs/current-translation-pipeline.md docs/translation-quality-context-strategy.md
git commit -m "Document translation brief workflow"
```

## Acceptance Criteria

- `translate-entry-preview-mod --brief PATH` uses confirmed brief names as highest-priority name seeds and prompt context.
- `translate-entry-loop` creates/updates `mod_translation_brief.json` by default under work-dir.
- Failed or needs-review rows do not update the brief.
- Conflicting accepted name translations create `open_questions` and do not overwrite confirmed names.
- Loop manifest records `brief_path` and `brief_version`.
- Full test suite and ruff pass.
