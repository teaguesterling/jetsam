"""Repository state snapshot builder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from jetsam.git.parsers import (
    StatusResult,
    parse_remote_url,
    parse_stash_list,
    parse_status,
)
from jetsam.git.wrapper import run_git_sync


def _is_jetsam_path(path: str) -> bool:
    """True if a status path belongs to jetsam's own state dir (.jetsam/).

    git reports the untracked dir as ".jetsam/" in normal mode and individual
    files like ".jetsam/plans/p_x.json" under -uall, so match both the dir
    itself and anything beneath it.
    """
    return path == ".jetsam" or path.rstrip("/") == ".jetsam" or path.startswith(".jetsam/")


@dataclass
class PRInfo:
    """Pull request information for the current branch."""

    number: int
    state: str
    title: str = ""
    url: str = ""
    checks: str = ""  # "passing", "failing", "pending", ""
    reviews: str = ""  # "approved", "changes_requested", ""
    mergeable: bool = False


@dataclass
class WorktreeInfo:
    """Minimal worktree info embedded in RepoState."""

    active: bool  # True if inside a secondary worktree
    root: str  # Main worktree path
    current: str  # Current worktree path


@dataclass
class RepoState:
    """Complete snapshot of repository state."""

    branch: str
    upstream: str | None
    default_branch: str
    dirty: bool
    staged: list[str]
    unstaged: list[str]
    untracked: list[str]
    ahead: int
    behind: int
    stash_count: int
    platform: str  # "github", "gitlab", "unknown"
    remote: str  # "owner/repo"
    remote_url: str
    pr: PRInfo | None = None
    head_sha: str = ""
    repo_root: str = ""
    worktree: WorktreeInfo | None = None

    # Computed fields for plan validation
    _state_hash: str = field(default="", repr=False)

    def compute_hash(
        self,
        scope: list[str] | None = None,
        exclude_remote_tracking: bool = False,
    ) -> str:
        """Compute a hash of the state for plan validation.

        If scope is provided, only hash state related to those files
        (ahead/behind are never included in scoped hashes).
        If exclude_remote_tracking is True, omit ahead/behind from unscoped hashes.
        This is used by sync/finish plans where fetch legitimately changes these values.
        """
        data: dict[str, object]
        if scope:
            # Only hash state that could affect the scoped files
            relevant_staged = [f for f in self.staged if f in scope]
            relevant_unstaged = [f for f in self.unstaged if f in scope]
            data = {
                "branch": self.branch,
                "head_sha": self.head_sha,
                "staged": sorted(relevant_staged),
                "unstaged": sorted(relevant_unstaged),
            }
        else:
            # Untracked files are deliberately excluded from the hash. They never
            # affect the safety of unscoped verbs (start/sync/finish/tidy/ship/
            # release don't touch untracked files), and agent-runtime dirs that
            # sit untracked and churn between plan and confirm (e.g. .kibitzer/,
            # .bird/) would otherwise invalidate every plan with stale_plan — the
            # same failure #12 fixed for jetsam's own .jetsam/, now generalized.
            # `dirty` is tracked-only here so untracked churn can't flip it either
            # (staged/unstaged already capture tracked state).
            data = {
                "branch": self.branch,
                "head_sha": self.head_sha,
                "dirty": bool(self.staged or self.unstaged),
                "staged": sorted(self.staged),
                "unstaged": sorted(self.unstaged),
            }
            if not exclude_remote_tracking:
                data["ahead"] = self.ahead
                data["behind"] = self.behind
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-serializable dict."""
        d = asdict(self)
        d.pop("_state_hash", None)
        return d


def build_state(cwd: str | None = None) -> RepoState:
    """Build a complete repository state snapshot.

    This runs several git commands to gather state. It's cheap (< 50ms)
    and should be called before any workflow verb.
    """
    # Get status (branch, staged, unstaged, untracked)
    status_result = run_git_sync(
        ["status", "--porcelain=v2", "--branch"], cwd=cwd
    )
    status = parse_status(status_result.stdout) if status_result.ok else _empty_status()

    # Get stash count
    stash_result = run_git_sync(["stash", "list"], cwd=cwd)
    stash_count = parse_stash_list(stash_result.stdout) if stash_result.ok else 0

    # Get default branch
    default_branch = _detect_default_branch(cwd)

    # Get remote URL and platform
    remote_result = run_git_sync(["remote", "get-url", "origin"], cwd=cwd)
    remote_url = remote_result.stdout.strip() if remote_result.ok else ""
    platform, remote = parse_remote_url(remote_url) if remote_url else ("unknown", "")

    # Get HEAD sha
    head_result = run_git_sync(["rev-parse", "HEAD"], cwd=cwd)
    head_sha = head_result.stdout.strip() if head_result.ok else ""

    # Get repo root
    root_result = run_git_sync(["rev-parse", "--show-toplevel"], cwd=cwd)
    repo_root = root_result.stdout.strip() if root_result.ok else ""

    # Detect worktree state
    worktree_info = _detect_worktree_info(cwd)

    # jetsam stores its own plans/config under .jetsam/. That directory is
    # untracked unless the repo gitignores it, and writing a plan creates or
    # mutates it between plan-creation and confirm. Because the state hash
    # counts untracked files, jetsam's own bookkeeping would otherwise
    # invalidate every plan (stale_plan on confirm). Exclude jetsam's own paths
    # so repo state — and its hash — never depends on jetsam's internals.
    staged = [f.path for f in status.staged if not _is_jetsam_path(f.path)]
    unstaged = [f.path for f in status.unstaged if not _is_jetsam_path(f.path)]
    untracked = [p for p in status.untracked if not _is_jetsam_path(p)]
    dirty = bool(staged or unstaged or untracked)

    state = RepoState(
        branch=status.branch.head,
        upstream=status.branch.upstream,
        default_branch=default_branch,
        dirty=dirty,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        ahead=status.branch.ahead,
        behind=status.branch.behind,
        stash_count=stash_count,
        platform=platform,
        remote=remote,
        remote_url=remote_url,
        head_sha=head_sha,
        repo_root=repo_root,
        worktree=worktree_info,
    )
    state._state_hash = state.compute_hash()
    return state


def _detect_default_branch(cwd: str | None = None) -> str:
    """Detect the default branch (main or master)."""
    # Try remote HEAD first
    result = run_git_sync(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=cwd)
    if result.ok:
        ref = result.stdout.strip()
        # refs/remotes/origin/main -> main
        return ref.split("/")[-1]

    # Fall back to checking if main or master exists
    for name in ("main", "master"):
        check = run_git_sync(["rev-parse", "--verify", f"refs/heads/{name}"], cwd=cwd)
        if check.ok:
            return name

    # Last resort
    return "main"


def _detect_worktree_info(cwd: str | None = None) -> WorktreeInfo | None:
    """Detect if we're in a worktree setup."""
    from jetsam.worktree.integration import detect_worktree

    wt_state = detect_worktree(cwd=cwd)
    if wt_state is None:
        return None
    return WorktreeInfo(
        active=wt_state.active,
        root=wt_state.root,
        current=wt_state.current,
    )


def _empty_status() -> StatusResult:
    from jetsam.git.parsers import BranchInfo

    return StatusResult(branch=BranchInfo(head="HEAD"))
