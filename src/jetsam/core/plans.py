"""Plan storage, validation, and TTL management."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from jetsam.core.planner import Plan, PlanStep

PLAN_TTL_SECONDS = 300  # 5 minutes


def generate_plan_id() -> str:
    """Generate a short unique plan ID."""
    return f"p_{secrets.token_hex(4)}"


class PlanStore:
    """Stores plans on disk with TTL validation.

    Plans are stored as JSON in .jetsam/plans/ with a 5-minute TTL.
    For CLI interactive flow, plans live in-memory and never hit disk.
    """

    def __init__(self, repo_root: str) -> None:
        self.plans_dir = Path(repo_root) / ".jetsam" / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def save(self, plan: Plan) -> None:
        """Save a plan to disk."""
        data = {
            "plan_id": plan.plan_id,
            "verb": plan.verb,
            "steps": [s.to_dict() for s in plan.steps],
            "state_hash": plan.state_hash,
            "scope": plan.scope,
            "warnings": plan.warnings,
            "params": plan.params,
            "created_at": time.time(),
        }
        path = self.plans_dir / f"{plan.plan_id}.json"
        path.write_text(json.dumps(data, indent=2))

    def load(self, plan_id: str) -> Plan | None:
        """Load a plan from disk. Returns None if not found or expired."""
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
            warnings=data.get("warnings", []),
            params=data.get("params", {}),
        )

    def delete(self, plan_id: str) -> None:
        """Delete a plan from disk."""
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
