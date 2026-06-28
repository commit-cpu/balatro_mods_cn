from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class LoopRoundArtifacts:
    round_index: int
    preview: Path
    rerun: Path
    target: Path
    audit: Path
    rerun_keys: Path


def default_loop_work_dir(repo: Path) -> Path:
    name = _safe_artifact_name(repo.name or "mod")
    return Path("data/artifacts") / f"{name}_entry_translate_loop"


def loop_round_artifacts(work_dir: Path, round_index: int) -> LoopRoundArtifacts:
    prefix = f"round_{round_index:02d}"
    return LoopRoundArtifacts(
        round_index=round_index,
        preview=work_dir / f"{prefix}_preview.jsonl",
        rerun=work_dir / f"{prefix}_rerun.jsonl",
        target=work_dir / f"{prefix}_zh_CN.lua",
        audit=work_dir / f"{prefix}_audit.json",
        rerun_keys=work_dir / f"{prefix}_rerun_keys.txt",
    )


def audit_has_rerunnable_issues(report: dict[str, Any]) -> bool:
    if _items(report.get("failed_rows")):
        return True
    if _items(report.get("needs_review_rows")):
        return True
    if _items(report.get("label_name_mismatches")):
        return True
    if _items(report.get("name_inconsistencies")):
        return True
    for section in ("residual_english", "untranslated_units"):
        for item in _items(report.get(section)):
            if item.get("severity") != "review":
                return True
    return False


def write_loop_manifest(
    *,
    path: Path,
    repo: Path,
    source: str,
    output: Path,
    work_dir: Path,
    max_rounds: int,
    completed_rounds: int,
    stopped_reason: str,
    rounds: list[LoopRoundArtifacts],
    final_audit_summary: dict[str, Any] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo": str(repo),
        "source": source,
        "output": str(output),
        "work_dir": str(work_dir),
        "max_rounds": max_rounds,
        "completed_rounds": completed_rounds,
        "stopped_reason": stopped_reason,
        "final_audit_summary": final_audit_summary or {},
        "rounds": [
            {
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(round_artifacts).items()
            }
            for round_artifacts in rounds
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_artifact_name(value: str) -> str:
    lowered = value.strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return safe or "mod"


def _items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
