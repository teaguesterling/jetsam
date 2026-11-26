"""Worktree detection and management."""

from __future__ import annotations

import os
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


# --- Submodule alternates guard ------------------------------------------
#
# A submodule store in one worktree can borrow objects from a submodule store
# in another worktree through ``objects/info/alternates`` (for example after
# ``git submodule update --reference <other tree>``). The lender store lives
# in ``<common>/worktrees/<name>/modules/``. ``git worktree remove`` and
# ``git worktree prune`` delete that directory, and the borrower then fails
# with "unable to normalize alternate object path". The same rule is in
# git-wt (README, "Submodule alternates guard").


def common_git_dir(cwd: str | None = None) -> str | None:
    """The repo's common git dir, absolute and resolved."""
    result = run_git_sync(["rev-parse", "--git-common-dir"], cwd=cwd)
    if not result.ok:
        return None
    common = result.stdout.strip()
    if not os.path.isabs(common):
        common = os.path.join(cwd or os.getcwd(), common)
    return os.path.realpath(common)


def _worktree_admin_dirs(common: str) -> list[str]:
    base = os.path.join(common, "worktrees")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [os.path.join(base, n) for n in names if os.path.isdir(os.path.join(base, n))]


def _back_pointer(admin_dir: str) -> str | None:
    """The worktree folder an admin dir points at (from its ``gitdir`` file)."""
    try:
        with open(os.path.join(admin_dir, "gitdir")) as f:
            dotgit = f.read().strip()
    except OSError:
        return None
    return os.path.realpath(os.path.dirname(dotgit)) if dotgit else None


def worktree_admin_dir(worktree_path: str, common: str) -> str | None:
    """``<common>/worktrees/<name>`` for a worktree, found from the back-pointer
    files, so it works when the worktree folder is gone."""
    target = os.path.realpath(worktree_path)
    for d in _worktree_admin_dirs(common):
        if _back_pointer(d) == target:
            return os.path.realpath(d)
    return None


def stale_worktree_admin_dirs(common: str) -> list[tuple[str, str | None]]:
    """Admin dirs that ``git worktree prune`` deletes: no ``gitdir`` file, or a
    worktree folder that is gone, and not locked. Returns (admin_dir, path)."""
    stale: list[tuple[str, str | None]] = []
    for d in _worktree_admin_dirs(common):
        if os.path.exists(os.path.join(d, "locked")):
            continue
        path = _back_pointer(d)
        if path is None or not os.path.exists(path):
            stale.append((os.path.realpath(d), path))
    return stale


def _inside(path: str, root: str | None) -> bool:
    return root is not None and (path + os.sep).startswith(root + os.sep)


def find_alternates_into(
    admin_dir: str, worktree_path: str | None, common: str,
) -> list[tuple[str, str]]:
    """Alternates entries in OTHER worktrees' stores that point into a worktree.

    Returns (alternates file, resolved target) pairs. A target counts when it
    is inside the worktree's admin dir or its folder. Paths are compared after
    realpath, with a trailing separator, so tree "a" never matches "a-b".
    """
    wt = os.path.realpath(worktree_path) if worktree_path else None
    hits: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(common):
        if os.path.basename(dirpath) == "objects":
            # Skip loose-object and pack dirs; keep objects/info.
            dirnames[:] = [d for d in dirnames if d == "info"]
        info_dir = dirpath.endswith(os.path.join(os.sep + "objects", "info"))
        if "alternates" not in filenames or not info_dir:
            continue
        f = os.path.realpath(os.path.join(dirpath, "alternates"))
        if _inside(f, admin_dir) or _inside(f, wt):
            continue  # the worktree's own stores go away with it
        objdir = os.path.dirname(os.path.dirname(f))
        with open(f) as fh:
            for line in fh.read().splitlines():
                if not line or line.startswith("#"):
                    continue
                target = os.path.realpath(os.path.join(objdir, line))
                if _inside(target, admin_dir) or _inside(target, wt):
                    hits.append((f, target))
    return hits


def _connected(store: str) -> bool:
    result = run_git_sync(
        ["--git-dir", store, "fsck", "--connectivity-only", "--no-dangling"],
    )
    return result.ok


def repoint_alternates(
    admin_dir: str, worktree_path: str | None, common: str,
    hits: list[tuple[str, str]],
) -> str | None:
    """Point each hit at the same path under the common dir (the primary
    store), then fsck each borrower. On any failure, restore every changed
    file and return an error message. Returns None on success."""
    wt = os.path.realpath(worktree_path) if worktree_path else None
    originals: dict[str, str] = {}
    error: str | None = None
    for f in dict.fromkeys(f for f, _ in hits):
        with open(f) as fh:
            originals[f] = fh.read()
        objdir = os.path.dirname(os.path.dirname(f))
        lines = []
        for line in originals[f].splitlines():
            if line and not line.startswith("#"):
                target = os.path.realpath(os.path.join(objdir, line))
                if _inside(target, admin_dir):
                    new = os.path.join(common, os.path.relpath(target, admin_dir))
                    if not os.path.isdir(new):
                        error = f"no primary store at {new} for {f}"
                        break
                    line = new
                elif _inside(target, wt):
                    error = f"{f} points into the worktree folder, not its git dir; cannot repoint"
                    break
            lines.append(line)
        if error:
            break
        with open(f, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        if not _connected(os.path.dirname(os.path.dirname(os.path.dirname(f)))):
            error = f"after repoint, {f} is missing objects that only the removed store has"
            break
    if error:
        for f, text in originals.items():
            with open(f, "w") as fh:
                fh.write(text)
        return error + "; restored the original alternates files"
    return None
