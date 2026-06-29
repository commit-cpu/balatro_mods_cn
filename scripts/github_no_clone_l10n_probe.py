#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.github.no_clone_l10n_probe import (
    GitHubApi,
    analyze_repository_no_clone,
    canonical_repo_from_meta,
    create_empty_zh_file_once,
    load_index_items,
    parse_github_repo_url,
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
    args = parser.parse_args()

    load_dotenv()
    token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_PAT")
    )
    if not token:
        raise SystemExit("Missing GITHUB_TOKEN, GH_TOKEN, or GITHUB_PAT.")

    items = load_index_items(args.index, args.limit)
    client = GitHubApi(token)
    report: dict[str, Any] = {
        "index": str(args.index),
        "limit": args.limit,
        "items": [],
        "test_commit": None,
    }

    try:
        github_user = client.current_user()
        report["github_user"] = github_user
        did_test_commit = False

        for index, item in enumerate(items, 1):
            url = str(item.get("github_repo_url") or "")
            name = str(item.get("name") or "")
            row: dict[str, Any] = {
                "index": index,
                "name": name,
                "url": url,
                "upstream": "",
                "canonical_upstream": "",
                "fork": "",
                "fork_status": "not_requested",
                "analysis": {},
                "error": None,
            }
            try:
                owner, repo = parse_github_repo_url(url)
                row["upstream"] = f"{owner}/{repo}"
                row["fork"] = f"{github_user}/{repo}"

                analysis, upstream_meta = analyze_repository_no_clone(
                    client=client,
                    owner=owner,
                    repo=repo,
                )
                canonical_owner, canonical_repo = canonical_repo_from_meta(
                    upstream_meta,
                    fallback_owner=owner,
                    fallback_repo=repo,
                )
                row["canonical_upstream"] = f"{canonical_owner}/{canonical_repo}"
                row["fork"] = f"{github_user}/{canonical_repo}"
                row["analysis"] = analysis.to_dict()

                fork_meta: dict[str, Any] | None = None
                if args.fork or (
                    args.create_empty_zh_once
                    and not did_test_commit
                    and analysis.status == "missing_zh_CN"
                    and analysis.details
                ):
                    fork_meta, fork_status = client.ensure_fork(
                        canonical_owner,
                        canonical_repo,
                        github_user,
                    )
                    row["fork_status"] = fork_status

                if (
                    args.create_empty_zh_once
                    and not did_test_commit
                    and fork_meta is not None
                    and analysis.status == "missing_zh_CN"
                    and analysis.details
                ):
                    target_path = analysis.details[0].target_path
                    default_branch = str(
                        fork_meta.get("default_branch")
                        or upstream_meta.get("default_branch")
                        or "main"
                    )
                    existing = client.file_text(
                        github_user,
                        repo,
                        target_path,
                        args.branch,
                    )
                    if existing is None:
                        commit_info = create_empty_zh_file_once(
                            client=client,
                            fork_owner=github_user,
                            repo=canonical_repo,
                            default_branch=default_branch,
                            target_path=target_path,
                            branch=args.branch,
                        )
                        commit_info["upstream"] = row["upstream"]
                        commit_info["canonical_upstream"] = row["canonical_upstream"]
                        commit_info["created_file"] = True
                    else:
                        commit_info = {
                            "repo": row["fork"],
                            "upstream": row["upstream"],
                            "canonical_upstream": row["canonical_upstream"],
                            "branch": args.branch,
                            "path": target_path,
                            "created_file": False,
                            "commit": None,
                        }
                    row["test_commit"] = commit_info
                    report["test_commit"] = commit_info
                    did_test_commit = True
            except Exception as exc:
                row["error"] = str(exc)

            report["items"].append(row)
            _print_row(row, index, len(items))
    finally:
        client.close()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
