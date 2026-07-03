"""Plan storage, validation, and TTL management."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from jetsam.core.planner import Plan, PlanStep

PLAN_TTL_SECONDS = 300  # 5 minutes

# A plan id is exactly ``p_`` followed by lowercase hex (see generate_plan_id).
# Validated before it is ever joined into a filesystem path so a crafted id
# (e.g. "../etc/passwd") cannot escape the plans directory (issue #19).
_PLAN_ID_RE = re.compile(r"p_[0-9a-f]+")


def generate_plan_id() -> str:
    """Generate a short unique plan ID."""
    return f"p_{secrets.token_hex(4)}"


def _is_valid_plan_id(plan_id: object) -> bool:
    """True only for the ids generate_plan_id() produces (safe as a path part)."""
    return isinstance(plan_id, str) and _PLAN_ID_RE.fullmatch(plan_id) is not None


def default_plans_dir() -> Path:
    """Resolve the per-user directory where plans are stored.

    Decoupled from any repo/cwd so a plan saved while working in repo A is
    still found when confirm() runs after the server's cwd has moved to repo B
    (issue #17). Uses ``$XDG_STATE_HOME/jetsam/plans`` when set, otherwise
    ``~/.local/state/jetsam/plans``.
    """
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "jetsam" / "plans"


class PlanStore:
    """Stores plans on disk with TTL validation.

    Plans are stored as JSON in a fixed per-user directory (see
    default_plans_dir), keyed by their unique plan_id, with a 5-minute TTL.
    The location intentionally does NOT depend on any repo/cwd. For the CLI
    interactive flow, plans live in-memory and never hit disk.
    """

    def __init__(self) -> None:
        self.plans_dir = default_plans_dir()
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def save(self, plan: Plan) -> None:
        """Save a plan to disk. Raises ValueError on a malformed plan_id."""
        if not _is_valid_plan_id(plan.plan_id):
            raise ValueError(f"invalid plan_id: {plan.plan_id!r}")
        data = {
            "plan_id": plan.plan_id,
            "verb": plan.verb,
            "steps": [s.to_dict() for s in plan.steps],
            "state_hash": plan.state_hash,
            "scope": plan.scope,
            "exclude_remote_tracking": plan.exclude_remote_tracking,
            "warnings": plan.warnings,
            "params": plan.params,
            "repo_root": plan.repo_root,
            "created_at": time.time(),
        }
        path = self.plans_dir / f"{plan.plan_id}.json"
        path.write_text(json.dumps(data, indent=2))

    def load(self, plan_id: str) -> Plan | None:
        """Load a plan from disk. Returns None if not found, expired, or invalid."""
        if not _is_valid_plan_id(plan_id):
            return None
        path = self.plans_dir / f"{plan_id}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        # Check TTL
        created_at = data.get("created_at", 0)
        if time.time() - created_at > PLAN_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None

        steps = [
            PlanStep(action=s["action"], params={k: v for k, v in s.items() if k != "action"})
            for s in data.get("steps", [])
        ]

        return Plan(
            plan_id=data["plan_id"],
            verb=data["verb"],
            steps=steps,
            state_hash=data["state_hash"],
            scope=data.get("scope"),
            exclude_remote_tracking=data.get("exclude_remote_tracking", False),
            warnings=data.get("warnings", []),
            params=data.get("params", {}),
            repo_root=data.get("repo_root", ""),
        )

    def delete(self, plan_id: str) -> None:
        """Delete a plan from disk. No-op for a malformed plan_id."""
        if not _is_valid_plan_id(plan_id):
            return
        path = self.plans_dir / f"{plan_id}.json"
        path.unlink(missing_ok=True)

    def cleanup_expired(self) -> int:
        """Remove expired plans. Returns count removed."""
        removed = 0
        now = time.time()
        for path in self.plans_dir.glob("p_*.json"):
            try:
                data = json.loads(path.read_text())
                if now - data.get("created_at", 0) > PLAN_TTL_SECONDS:
                    path.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def update_plan(
    plan: Plan,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Update a plan's parameters and regenerate steps.

    Returns a diff of what changed.
    """
    import fnmatch

    diff: dict[str, Any] = {}

    if message is not None:
        old_msg = plan.params.get("message")
        plan.params["message"] = message
        diff["message"] = {"old": old_msg, "new": message}
        # Update commit step
        for step in plan.steps:
            if step.action == "commit":
                step.params["message"] = message
        # Update PR title if it matches old message
        for step in plan.steps:
            if step.action == "pr_create" and step.params.get("title") == old_msg:
                step.params["title"] = message

    if exclude is not None:
        # Remove files matching the exclude pattern from stage steps
        for step in plan.steps:
            if step.action == "stage":
                old_files = step.params.get("files", [])
                new_files = [f for f in old_files if not fnmatch.fnmatch(f, exclude)]
                removed = [f for f in old_files if f not in new_files]
                if removed:
                    step.params["files"] = new_files
                    diff["removed_files"] = removed
                    # Update file count in commit step
                    for cs in plan.steps:
                        if cs.action == "commit":
                            cs.params["file_count"] = len(new_files)

    if include is not None or files is not None:
        # Add files — this requires the full file list from state
        # For now, just record in diff
        diff["note"] = "include/files changes require re-planning with current state"

    return diff
