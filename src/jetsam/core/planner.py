"""Plan generation from state + intent."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any

from jetsam.core.state import RepoState


@dataclass
class PlanStep:
    """A single step in a plan."""

    action: str  # "stage", "commit", "push", "pr_create", "pr_update", "fetch", "rebase", etc.
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, **self.params}


@dataclass
class Plan:
    """A mutable execution plan."""

    plan_id: str
    verb: str  # "save", "ship", "sync", etc.
    steps: list[PlanStep]
    state_hash: str
    scope: list[str] | None = None  # files this plan touches
    warnings: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "verb": self.verb,
            "steps": [s.to_dict() for s in self.steps],
            "warnings": self.warnings,
        }


def plan_save(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
) -> Plan:
    """Generate a plan for the 'save' verb (stage + commit)."""
    # Determine which files to stage
    target_files = _resolve_files(state, include, exclude, files)
    warnings: list[str] = []

    if not target_files and not state.staged:
        warnings.append("No files to stage or commit")

    # Determine commit message
    if not message:
        message = _generate_message_heuristic(target_files)

    steps: list[PlanStep] = []

    if target_files:
        steps.append(PlanStep(action="stage", params={"files": target_files}))

    all_staged = list(set(state.staged + target_files))
    steps.append(
        PlanStep(
            action="commit",
            params={"message": message, "file_count": len(all_staged)},
        )
    )

    scope = target_files or state.staged

    return Plan(
        plan_id=plan_id,
        verb="save",
        steps=steps,
        state_hash=state.compute_hash(scope=scope),
        scope=scope,
        warnings=warnings,
        params={"message": message, "include": include, "exclude": exclude, "files": files},
    )


def plan_sync(
    state: RepoState,
    plan_id: str,
    strategy: str | None = None,
) -> Plan:
    """Generate a plan for the 'sync' verb (fetch + rebase/merge + push)."""
    steps: list[PlanStep] = []
    warnings: list[str] = []

    if state.dirty:
        warnings.append("Working tree is dirty — changes will be stashed during sync")
        steps.append(PlanStep(action="stash", params={"message": "jetsam sync auto-stash"}))

    # Fetch
    steps.append(PlanStep(action="fetch", params={"remote": "origin"}))

    # Rebase or merge
    is_default = state.branch == state.default_branch
    actual_strategy = strategy or ("merge" if is_default else "rebase")

    if state.upstream:
        if actual_strategy == "rebase":
            steps.append(
                PlanStep(action="rebase", params={"onto": state.upstream})
            )
        else:
            steps.append(
                PlanStep(action="merge", params={"from": state.upstream})
            )
    elif not is_default:
        # No upstream, rebase onto default
        default_remote = f"origin/{state.default_branch}"
        if actual_strategy == "rebase":
            steps.append(
                PlanStep(action="rebase", params={"onto": default_remote})
            )
        else:
            steps.append(
                PlanStep(action="merge", params={"from": default_remote})
            )

    # Push if there are local commits or after rebase
    if state.ahead > 0 or not is_default:
        steps.append(
            PlanStep(
                action="push",
                params={
                    "branch": state.branch,
                    "remote": "origin",
                    "set_upstream": state.upstream is None,
                },
            )
        )

    if state.dirty:
        steps.append(PlanStep(action="stash_pop"))

    return Plan(
        plan_id=plan_id,
        verb="sync",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={"strategy": strategy},
    )


def plan_ship(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    to: str | None = None,
    open_pr: bool = True,
    merge: bool = False,
) -> Plan:
    """Generate a plan for the 'ship' verb (stage + commit + push + PR)."""
    steps: list[PlanStep] = []
    warnings: list[str] = []
    target_branch = to or state.default_branch

    # Stage files
    target_files = _resolve_files(state, include, exclude)
    if target_files:
        steps.append(PlanStep(action="stage", params={"files": target_files}))

    # Commit
    all_staged = list(set(state.staged + target_files))
    if all_staged or state.dirty:
        if not message:
            message = _generate_message_heuristic(all_staged)
        steps.append(
            PlanStep(
                action="commit",
                params={"message": message, "file_count": len(all_staged)},
            )
        )
    elif not message:
        message = ""

    # Push
    steps.append(
        PlanStep(
            action="push",
            params={
                "branch": state.branch,
                "remote": "origin",
                "set_upstream": state.upstream is None,
            },
        )
    )

    # PR
    if open_pr:
        if state.pr:
            steps.append(
                PlanStep(
                    action="pr_update",
                    params={"number": state.pr.number},
                )
            )
        else:
            steps.append(
                PlanStep(
                    action="pr_create",
                    params={
                        "title": message or state.branch,
                        "base": target_branch,
                    },
                )
            )

    # Merge
    if merge:
        if state.branch == target_branch:
            warnings.append("Cannot merge branch into itself")
        else:
            steps.append(
                PlanStep(
                    action="pr_merge",
                    params={"base": target_branch},
                )
            )

    # Warnings
    if state.behind > 0:
        warnings.append(
            f"Branch is {state.behind} commits behind {state.upstream or state.default_branch}"
        )

    scope = target_files or state.staged
    return Plan(
        plan_id=plan_id,
        verb="ship",
        steps=steps,
        state_hash=state.compute_hash(scope=scope),
        scope=scope,
        warnings=warnings,
        params={
            "message": message,
            "include": include,
            "exclude": exclude,
            "to": to,
            "open_pr": open_pr,
            "merge": merge,
        },
    )


def _resolve_files(
    state: RepoState,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
) -> list[str]:
    """Resolve which files to stage based on include/exclude/files patterns."""
    if files:
        return files

    # Pool of candidates: unstaged + untracked (staged are already staged)
    candidates = state.unstaged + state.untracked

    if include:
        candidates = [f for f in candidates if fnmatch.fnmatch(f, include)]

    if exclude:
        candidates = [f for f in candidates if not fnmatch.fnmatch(f, exclude)]

    # If no include pattern, default to modified tracked files only (not untracked)
    if not include and not files:
        candidates = [f for f in candidates if f in state.unstaged]

    return candidates


def _generate_message_heuristic(files: list[str]) -> str:
    """Generate a simple commit message from file list."""
    if not files:
        return "update"

    if len(files) == 1:
        return f"update {files[0]}"

    # Group by directory
    dirs = set()
    for f in files:
        parts = f.rsplit("/", 1)
        if len(parts) > 1:
            dirs.add(parts[0])

    if len(dirs) == 1:
        return f"update {next(iter(dirs))}/ ({len(files)} files)"

    return f"update {len(files)} files"
