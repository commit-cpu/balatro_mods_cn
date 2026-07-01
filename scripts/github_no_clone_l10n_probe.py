#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.github.no_clone_l10n_probe import (
    load_index_items,
    run_github_l10n_probe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Balatro mod localization status through GitHub API without cloning."
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data/repos/balatro-mod-index/mods/all.json"),
        help="Mod index JSON file.",
    )
    parser.add_argument("--limit", type=int, default=10, help="Number of repos to inspect.")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/artifacts/github_no_clone_l10n_probe/report.json"),
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--fork",
        action="store_true",
        help="Fork each inspected repository to the authenticated GitHub account.",
    )
    parser.add_argument(
        "--create-empty-zh-once",
        action="store_true",
        help=(
            "For the first repo with source localization but no zh_CN.lua, create "
            "an empty zh_CN.lua on a test branch in the fork."
        ),
    )
    parser.add_argument(
        "--branch",
        default="codex-test-empty-zh-cn",
        help="Branch name used by --create-empty-zh-once.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/artifacts/github_no_clone_l10n_probe/cache"),
        help="Local cache directory for GitHub GET responses.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached GitHub GET responses and rewrite cache files.",
    )
    parser.add_argument(
        "--cache-ttl-seconds",
        type=int,
        default=6 * 60 * 60,
        help="Use cached GitHub GET responses newer than this TTL.",
    )
    args = parser.parse_args()

    load_dotenv()
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not token:
        raise SystemExit("Missing GITHUB_TOKEN, GH_TOKEN, or GITHUB_PAT.")

    report = run_github_l10n_probe(
        token=token,
        index_path=args.index,
        report_path=args.report,
        limit=args.limit,
        fork=args.fork,
        create_empty_zh_once=args.create_empty_zh_once,
        branch=args.branch,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
        cache_ttl_seconds=args.cache_ttl_seconds,
    )
    for index, row in enumerate(report["items"], 1):
        _print_row(row, index, len(report["items"]))
    print(f"Report written: {args.report}")
    if report["test_commit"]:
        print("Test commit:")
        print(json.dumps(report["test_commit"], ensure_ascii=False, indent=2))


def _print_row(row: dict[str, Any], index: int, total: int) -> None:
    analysis = row.get("analysis")
    summary = analysis.get("summary") if isinstance(analysis, dict) else {}
    status = summary.get("status") if isinstance(summary, dict) else "error"
    print(
        f"[{index}/{total}] {row.get('name')} {row.get('upstream')} "
        f"fork={row.get('fork_status')} status={status}"
    )
    if isinstance(summary, dict) and summary:
        print(
            "  "
            f"source_units={summary.get('source_units', 0)} "
            f"zh_units={summary.get('zh_units', 0)} "
            f"missing={summary.get('missing_keys', 0)} "
            f"untranslated={summary.get('untranslated_keys', 0)} "
            f"residual={summary.get('residual_english', 0)}"
        )
    if row.get("error"):
        print(f"  error={row['error']}")


if __name__ == "__main__":
    main()
