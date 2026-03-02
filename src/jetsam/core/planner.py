"""Plan generation from state + intent."""

from __future__ import annotations

import fnmatch
import re
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


def plan_switch(
    state: RepoState,
    plan_id: str,
    branch: str,
    create: bool = False,
) -> Plan:
    """Generate a plan for the 'switch' verb (stash-aware branch switch)."""
    steps: list[PlanStep] = []
    warnings: list[str] = []

    if state.dirty:
        msg = f"jetsam switch from {state.branch}"
        steps.append(PlanStep(action="stash", params={"message": msg}))

    steps.append(PlanStep(action="checkout", params={"branch": branch, "create": create}))

    if state.dirty:
        steps.append(PlanStep(action="stash_pop"))
        warnings.append("Dirty changes will be stashed and restored on the target branch")

    return Plan(
        plan_id=plan_id,
        verb="switch",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={"branch": branch, "create": create},
    )


def plan_start(
    state: RepoState,
    plan_id: str,
    target: str,
    issue_title: str | None = None,
    branch_prefix: str = "",
    worktree: bool = False,
    base: str | None = None,
) -> Plan:
    """Generate a plan for the 'start' verb (begin work on issue/feature).

    Args:
        target: Issue number (e.g. "42") or branch name (e.g. "fix-parser").
        issue_title: Title of the issue (for slug generation if target is numeric).
        branch_prefix: Optional prefix for branch names (e.g. "feature/").
        worktree: If True, create a worktree instead of switching branches.
        base: Base branch to create from (default: default_branch).
    """
    steps: list[PlanStep] = []
    warnings: list[str] = []
    actual_base = base or state.default_branch

    # Determine branch name
    if target.isdigit():
        issue_num = int(target)
        if issue_title:
            slug = _slugify(issue_title)
            branch_name = f"{issue_num}-{slug}"
        else:
            branch_name = f"issue-{issue_num}"
    else:
        branch_name = target

    # Apply branch prefix
    if branch_prefix and not branch_name.startswith(branch_prefix):
        branch_name = f"{branch_prefix}{branch_name}"

    if worktree:
        steps.append(PlanStep(
            action="worktree_add",
            params={"branch": branch_name, "base": actual_base},
        ))
    else:
        if state.dirty:
            warnings.append("Dirty changes will be stashed before switching")
            steps.append(PlanStep(
                action="stash",
                params={"message": f"jetsam start: stash before {branch_name}"},
            ))

        steps.append(PlanStep(
            action="checkout",
            params={"branch": branch_name, "create": True, "start_point": actual_base},
        ))

        if state.dirty:
            steps.append(PlanStep(action="stash_pop"))

    return Plan(
        plan_id=plan_id,
        verb="start",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={
            "target": target,
            "branch": branch_name,
            "base": actual_base,
            "worktree": worktree,
        },
    )


def plan_finish(
    state: RepoState,
    plan_id: str,
    strategy: str = "squash",
    no_delete: bool = False,
    worktree_path: str | None = None,
) -> Plan:
    """Generate a plan for the 'finish' verb (merge PR, clean up branch).

    Args:
        strategy: Merge strategy ("squash", "merge", "rebase").
        no_delete: Skip branch deletion after merge.
        worktree_path: If in a worktree, path to remove.
    """
    steps: list[PlanStep] = []
    warnings: list[str] = []

    if state.branch == state.default_branch:
        warnings.append("Already on default branch — nothing to finish")
        return Plan(
            plan_id=plan_id,
            verb="finish",
            steps=[],
            state_hash=state.compute_hash(),
            warnings=warnings,
            params={"strategy": strategy, "no_delete": no_delete},
        )

    if state.dirty:
        warnings.append("Working tree has uncommitted changes")

    # Merge the PR if one exists
    if state.pr:
        steps.append(PlanStep(
            action="pr_merge",
            params={
                "number": state.pr.number,
                "strategy": strategy,
                "delete_branch": not no_delete,
            },
        ))

    # Switch back to default branch
    if worktree_path:
        steps.append(PlanStep(
            action="worktree_remove",
            params={"path": worktree_path},
        ))
    else:
        steps.append(PlanStep(
            action="checkout",
            params={"branch": state.default_branch},
        ))

    # Fetch to update refs after merge
    steps.append(PlanStep(action="fetch", params={"remote": "origin"}))

    # Delete branch locally (if not already deleted by merge)
    if not no_delete and not (state.pr and not worktree_path):
        # Only add explicit delete if pr_merge didn't handle it
        steps.append(PlanStep(
            action="branch_delete",
            params={"branch": state.branch},
        ))

    return Plan(
        plan_id=plan_id,
        verb="finish",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={
            "branch": state.branch,
            "strategy": strategy,
            "no_delete": no_delete,
        },
    )


def plan_release(
    state: RepoState,
    plan_id: str,
    tag: str,
    title: str | None = None,
    notes: str = "",
    draft: bool = False,
) -> Plan:
    """Generate a plan for the 'release' verb (tag + push tag + create release).

    Args:
        tag: Tag name (e.g. "v0.1.0").
        title: Release title (defaults to tag).
        notes: Release notes text.
        draft: Create as a draft release.
    """
    steps: list[PlanStep] = []
    warnings: list[str] = []
    actual_title = title or tag

    if state.dirty:
        warnings.append("Working tree has uncommitted changes")

    if state.branch != state.default_branch:
        warnings.append(f"Not on default branch ({state.default_branch})")

    # Check if tag already exists
    from jetsam.git.wrapper import run_git_sync

    tag_check = run_git_sync(["tag", "-l", tag], cwd=state.repo_root)
    if tag_check.ok and tag_check.stdout.strip():
        warnings.append(f"Tag {tag} already exists")
    else:
        steps.append(PlanStep(
            action="tag_create",
            params={"tag": tag, "message": actual_title},
        ))

    steps.append(PlanStep(
        action="push_tag",
        params={"tag": tag, "remote": "origin"},
    ))

    steps.append(PlanStep(
        action="release_create",
        params={"tag": tag, "title": actual_title, "notes": notes, "draft": draft},
    ))

    return Plan(
        plan_id=plan_id,
        verb="release",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={"tag": tag, "title": actual_title, "notes": notes, "draft": draft},
    )


def plan_tidy(
    state: RepoState,
    plan_id: str,
) -> Plan:
    """Generate a plan for the 'tidy' verb (prune merged branches + remotes)."""
    steps: list[PlanStep] = []
    warnings: list[str] = []

    # Prune stale remote-tracking refs
    steps.append(PlanStep(
        action="remote_prune",
        params={"remote": "origin"},
    ))

    # Prune local branches whose upstream is gone
    steps.append(PlanStep(action="prune_merged_branches"))

    # Prune stale worktree refs
    if state.worktree is not None:
        steps.append(PlanStep(action="worktree_prune"))

    return Plan(
        plan_id=plan_id,
        verb="tidy",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={},
    )


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a branch-name-safe slug.

    Examples:
        "Fix parser bug" -> "fix-parser-bug"
        "Add  feature!! (important)" -> "add-feature-important"
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    if len(text) > max_length:
        # Truncate at word boundary
        text = text[:max_length].rsplit("-", 1)[0]
    return text


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
