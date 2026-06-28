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
