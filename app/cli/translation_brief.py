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
    def empty(cls, *, mod_id: str, repo: Path, source: str) -> TranslationBrief:
        return cls(
            schema_version=BRIEF_SCHEMA_VERSION,
            mod_id=mod_id,
            locale=BRIEF_LOCALE,
            source={"repo": str(repo), "source": source},
        )


def default_brief_path(work_dir: Path) -> Path:
    return work_dir / BRIEF_FILENAME


def load_translation_brief(
    path: Path, *, mod_id: str, repo: Path, source: str
) -> TranslationBrief:
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
    payload = json.dumps(
        asdict(brief),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        if not _can_promote_name_entry(entry_key):
            if isinstance(source_name, str):
                brief.name_map.pop(source_name, None)
            continue
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


def _can_promote_name_entry(entry_key: object) -> bool:
    if not isinstance(entry_key, str):
        return False
    if entry_key.startswith("descriptions."):
        return True
    return entry_key.startswith("misc.labels.")


def _append_open_question(brief: TranslationBrief, question: dict[str, Any]) -> None:
    if question not in brief.open_questions:
        brief.open_questions.append(question)
