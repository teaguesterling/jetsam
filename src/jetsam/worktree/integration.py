"""Worktree detection and management."""

from __future__ import annotations

from dataclasses import dataclass, field

from jetsam.git.parsers import WorktreeEntry, parse_worktree_list
from jetsam.git.wrapper import run_git_sync


@dataclass
class WorktreeInfo:
    """Info about a single worktree."""

    path: str
    branch: str
    head: str
    is_main: bool = False
    prunable: bool = False


@dataclass
class WorktreeState:
    """Worktree state for the current repo."""

    active: bool  # True if currently inside a worktree (not the main checkout)
    mode: str  # "auto", "always", "never"
    root: str  # Main worktree path
    current: str  # Current worktree path
    main_path: str  # Path to the main worktree
    worktrees: list[WorktreeInfo] = field(default_factory=list)


def detect_worktree(cwd: str | None = None) -> WorktreeState | None:
    """Detect worktree state for the current repo.

    Returns None if worktrees aren't in use (single working tree).
    """
    result = run_git_sync(["worktree", "list", "--porcelain"], cwd=cwd)
    if not result.ok:
        return None

    entries = parse_worktree_list(result.stdout)
    if len(entries) <= 1:
        # No extra worktrees — not in worktree mode
        return None

    # Get current working directory's git root
    root_result = run_git_sync(["rev-parse", "--show-toplevel"], cwd=cwd)
    current_path = root_result.stdout.strip() if root_result.ok else ""

    # First entry is the main worktree
    main_entry = entries[0]
    infos: list[WorktreeInfo] = []
    for entry in entries:
        infos.append(WorktreeInfo(
            path=entry.path,
            branch=entry.branch,
            head=entry.head,
            is_main=(entry.path == main_entry.path),
            prunable=entry.prunable,
        ))

    is_active = current_path != main_entry.path

    return WorktreeState(
        active=is_active,
        mode="auto",
        root=main_entry.path,
        current=current_path,
        main_path=main_entry.path,
        worktrees=infos,
    )


def setup_shared_paths(repo_root: str, worktree_path: str) -> list[str]:
    """Symlink shared paths from main repo into a new worktree.

    Reads `.git-worktree-shared` from repo root (one path per line),
    and creates symlinks in the worktree pointing back to the main repo.

    Returns list of paths that were symlinked.
    """
    import os

    shared_file = os.path.join(repo_root, ".git-worktree-shared")
    if not os.path.isfile(shared_file):
        return []

    with open(shared_file) as f:
        paths = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    linked: list[str] = []
    for rel_path in paths:
        source = os.path.join(repo_root, rel_path)
        target = os.path.join(worktree_path, rel_path)

        # Skip if source doesn't exist
        if not os.path.exists(source):
            continue

        # Skip if target already exists (symlink or otherwise)
        if os.path.exists(target) or os.path.islink(target):
            continue

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(target), exist_ok=True)

        os.symlink(source, target)
        linked.append(rel_path)

    return linked


def list_worktrees(cwd: str | None = None) -> list[WorktreeEntry]:
    """List all worktrees."""
    result = run_git_sync(["worktree", "list", "--porcelain"], cwd=cwd)
    if not result.ok:
        return []
    return parse_worktree_list(result.stdout)


def create_worktree(
    path: str,
    branch: str,
    new_branch: bool = True,
    base: str | None = None,
    cwd: str | None = None,
) -> bool:
    """Create a new worktree.

    Args:
        path: Filesystem path for the new worktree.
        branch: Branch name for the worktree.
        new_branch: Create the branch if True.
        base: Base ref for the new branch (default: HEAD).
        cwd: Working directory.

    Returns:
        True on success.
    """
    args = ["worktree", "add"]
    if new_branch:
        args.extend(["-b", branch])
        args.append(path)
        if base:
            args.append(base)
    else:
        args.extend([path, branch])

    result = run_git_sync(args, cwd=cwd)
    return result.ok


def remove_worktree(path: str, force: bool = False, cwd: str | None = None) -> bool:
    """Remove a worktree.

    Args:
        path: Filesystem path of the worktree to remove.
        force: Force removal even if dirty.
        cwd: Working directory.

    Returns:
        True on success.
    """
    args = ["worktree", "remove", path]
    if force:
        args.append("--force")
    result = run_git_sync(args, cwd=cwd)
    return result.ok


def prune_worktrees(cwd: str | None = None) -> bool:
    """Prune stale worktree references.

    Returns:
        True on success.
    """
    result = run_git_sync(["worktree", "prune"], cwd=cwd)
    return result.ok
