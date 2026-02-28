"""Output formatting for human and JSON modes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class JetsamError:
    """Structured error response."""

    error: str
    message: str
    suggested_action: str | None = None
    recoverable: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"error": self.error, "message": self.message}
        if self.suggested_action:
            d["suggested_action"] = self.suggested_action
        d["recoverable"] = self.recoverable
        return d

    def format_human(self) -> str:
        lines = [f"  \u2717 {self.message}"]
        if self.suggested_action:
            lines.append(f"  Fix: jetsam {self.suggested_action}")
        return "\n".join(lines)


def format_json(data: Any) -> str:
    """Format data as JSON."""
    if hasattr(data, "to_dict"):
        data = data.to_dict()
    elif hasattr(data, "__dataclass_fields__"):
        data = asdict(data)
    return json.dumps(data, indent=2, default=str)


def format_human_status(state_dict: dict[str, Any]) -> str:
    """Format a state snapshot for human reading."""
    lines: list[str] = []

    branch = state_dict.get("branch", "unknown")
    upstream = state_dict.get("upstream", "")
    ahead = state_dict.get("ahead", 0)
    behind = state_dict.get("behind", 0)

    # Branch line
    branch_line = f"  On {branch}"
    if upstream:
        tracking = []
        if ahead:
            tracking.append(f"\u2191{ahead}")
        if behind:
            tracking.append(f"\u2193{behind}")
        if tracking:
            branch_line += f"  ({', '.join(tracking)} vs {upstream})"
        else:
            branch_line += f"  (tracking {upstream})"
    lines.append(branch_line)

    # Status
    staged = state_dict.get("staged", [])
    unstaged = state_dict.get("unstaged", [])
    untracked = state_dict.get("untracked", [])

    if not staged and not unstaged and not untracked:
        lines.append("  Clean working tree")
    else:
        if staged:
            lines.append(f"  Staged:    {', '.join(staged)}")
        if unstaged:
            lines.append(f"  Modified:  {', '.join(unstaged)}")
        if untracked:
            lines.append(f"  Untracked: {', '.join(untracked)}")

    stash = state_dict.get("stash_count", 0)
    if stash:
        lines.append(f"  Stash: {stash} {'entry' if stash == 1 else 'entries'}")

    # PR info
    pr = state_dict.get("pr")
    if pr and isinstance(pr, dict):
        pr_line = f"  PR #{pr['number']}: {pr.get('state', 'open')}"
        checks = pr.get("checks", "")
        if checks:
            pr_line += f"  checks: {checks}"
        lines.append(pr_line)

    return "\n".join(lines)


def format_human_log(entries: list[dict[str, Any]]) -> str:
    """Format log entries for human reading."""
    lines: list[str] = []
    for entry in entries:
        sha = entry.get("short_sha", entry.get("sha", "???")[:7])
        msg = entry.get("message", "")
        author = entry.get("author", "")
        lines.append(f"  {sha} {msg}  ({author})")
    return "\n".join(lines)


def format_human_diff_stat(stat_dict: dict[str, Any]) -> str:
    """Format diff stat for human reading."""
    files = stat_dict.get("file_stats", [])
    lines: list[str] = []
    for f in files:
        path = f.get("path", "")
        ins = f.get("insertions", 0)
        dels = f.get("deletions", 0)
        change = "+" * min(ins, 30) + "-" * min(dels, 30)
        lines.append(f"  {path}: {change}")

    total_ins = stat_dict.get("insertions", 0)
    total_dels = stat_dict.get("deletions", 0)
    total_files = stat_dict.get("files_changed", 0)
    lines.append(f"  {total_files} files, +{total_ins} -{total_dels}")
    return "\n".join(lines)
