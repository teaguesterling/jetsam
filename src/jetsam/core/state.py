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

    # Computed fields for plan validation
    _state_hash: str = field(default="", repr=False)

    def compute_hash(self, scope: list[str] | None = None) -> str:
        """Compute a hash of the state for plan validation.

        If scope is provided, only hash state related to those files.
        Otherwise hash the full state.
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
            data = {
                "branch": self.branch,
                "head_sha": self.head_sha,
                "dirty": self.dirty,
                "staged": sorted(self.staged),
                "unstaged": sorted(self.unstaged),
                "untracked": sorted(self.untracked),
                "ahead": self.ahead,
                "behind": self.behind,
            }
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

    state = RepoState(
        branch=status.branch.head,
        upstream=status.branch.upstream,
        default_branch=default_branch,
        dirty=status.dirty,
        staged=[f.path for f in status.staged],
        unstaged=[f.path for f in status.unstaged],
        untracked=status.untracked,
        ahead=status.branch.ahead,
        behind=status.branch.behind,
        stash_count=stash_count,
        platform=platform,
        remote=remote,
        remote_url=remote_url,
        head_sha=head_sha,
        repo_root=repo_root,
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


def _empty_status() -> StatusResult:
    from jetsam.git.parsers import BranchInfo

    return StatusResult(branch=BranchInfo(head="HEAD"))
