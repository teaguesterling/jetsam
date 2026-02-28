"""Parsers for git command output into structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Status parsing (git status --porcelain=v2 --branch) ---


@dataclass
class FileStatus:
    """Status of a single file."""

    path: str
    index_status: str  # status in index (staged area)
    worktree_status: str  # status in worktree
    original_path: str | None = None  # for renames


@dataclass
class BranchInfo:
    """Branch tracking info from status."""

    head: str  # current branch name or "(detached)"
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0


@dataclass
class StatusResult:
    """Parsed result of git status."""

    branch: BranchInfo
    staged: list[FileStatus] = field(default_factory=list)
    unstaged: list[FileStatus] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)

    @property
    def dirty(self) -> bool:
        return bool(self.staged or self.unstaged or self.untracked)


def parse_status(output: str) -> StatusResult:
    """Parse git status --porcelain=v2 --branch output."""
    branch = BranchInfo(head="HEAD")
    staged: list[FileStatus] = []
    unstaged: list[FileStatus] = []
    untracked: list[str] = []

    for line in output.splitlines():
        if line.startswith("# branch.head "):
            branch.head = line[len("# branch.head ") :]
        elif line.startswith("# branch.upstream "):
            branch.upstream = line[len("# branch.upstream ") :]
        elif line.startswith("# branch.ab "):
            match = re.match(r"# branch\.ab \+(\d+) -(\d+)", line)
            if match:
                branch.ahead = int(match.group(1))
                branch.behind = int(match.group(2))
        elif line.startswith("1 ") or line.startswith("2 "):
            # Ordinary (1) or rename/copy (2) entry
            if line.startswith("1 "):
                # 1 XY sub mH mI mW hH hI path
                parts = line.split(" ", 8)
                xy = parts[1]
                path = parts[8]
                orig = None
            else:
                # 2 XY sub mH mI mW hH hI Xscore path\torigPath
                parts = line.split(" ", 9)
                xy = parts[1]
                path_field = parts[9]
                if "\t" in path_field:
                    path, orig = path_field.split("\t", 1)
                else:
                    path = path_field
                    orig = None

            index_st = xy[0]
            work_st = xy[1]

            if index_st != ".":
                staged.append(
                    FileStatus(
                        path=path,
                        index_status=index_st,
                        worktree_status=".",
                        original_path=orig,
                    )
                )
            if work_st != ".":
                unstaged.append(
                    FileStatus(
                        path=path,
                        index_status=".",
                        worktree_status=work_st,
                        original_path=None,
                    )
                )
        elif line.startswith("? "):
            # Untracked file
            untracked.append(line[2:])
        elif line.startswith("u "):
            # Unmerged entry — treat as unstaged for now
            parts = line.split(" ", 10)
            path = parts[10]
            unstaged.append(
                FileStatus(path=path, index_status="U", worktree_status="U")
            )

    return StatusResult(branch=branch, staged=staged, unstaged=unstaged, untracked=untracked)


# --- Log parsing (git log --format) ---


@dataclass
class LogEntry:
    """A single commit log entry."""

    sha: str
    short_sha: str
    author: str
    date: str
    message: str


def parse_log(output: str) -> list[LogEntry]:
    """Parse git log with custom format.

    Expected format: git log --format='%H%x00%h%x00%an%x00%aI%x00%s'
    """
    entries: list[LogEntry] = []
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) >= 5:
            entries.append(
                LogEntry(
                    sha=parts[0],
                    short_sha=parts[1],
                    author=parts[2],
                    date=parts[3],
                    message=parts[4],
                )
            )
    return entries


# --- Diff stat parsing ---


@dataclass
class DiffStat:
    """Summary of a diff."""

    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    file_stats: list[DiffFileStat] = field(default_factory=list)


@dataclass
class DiffFileStat:
    """Per-file diff stat."""

    path: str
    insertions: int = 0
    deletions: int = 0


def parse_diff_stat(output: str) -> DiffStat:
    """Parse git diff --stat output."""
    stat = DiffStat()
    lines = output.strip().splitlines()

    for line in lines:
        # Summary line: " N files changed, X insertions(+), Y deletions(-)"
        summary_match = re.match(
            r"\s*(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
            line,
        )
        if summary_match:
            stat.files_changed = int(summary_match.group(1))
            stat.insertions = int(summary_match.group(2) or 0)
            stat.deletions = int(summary_match.group(3) or 0)
            continue

        # Per-file line: " path | N +++---"
        file_match = re.match(r"\s*(.+?)\s+\|\s+(\d+)\s+(\+*-*)", line)
        if file_match:
            path = file_match.group(1).strip()
            pluses = file_match.group(3).count("+")
            minuses = file_match.group(3).count("-")
            stat.file_stats.append(DiffFileStat(path=path, insertions=pluses, deletions=minuses))

    return stat


# --- Diff numstat parsing (machine-readable) ---


def parse_diff_numstat(output: str) -> DiffStat:
    """Parse git diff --numstat output."""
    stat = DiffStat()
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            ins = int(parts[0]) if parts[0] != "-" else 0
            dels = int(parts[1]) if parts[1] != "-" else 0
            path = parts[2]
            stat.file_stats.append(DiffFileStat(path=path, insertions=ins, deletions=dels))
            stat.insertions += ins
            stat.deletions += dels
            stat.files_changed += 1
    return stat


# --- Branch parsing ---


@dataclass
class BranchEntry:
    """A git branch."""

    name: str
    sha: str
    is_current: bool = False
    upstream: str | None = None


def parse_branches(output: str) -> list[BranchEntry]:
    """Parse git branch -vv output."""
    branches: list[BranchEntry] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        is_current = line.startswith("*")
        line = line[2:]  # strip "* " or "  "
        parts = line.split(None, 2)
        if len(parts) >= 2:
            name = parts[0]
            sha = parts[1]
            upstream = None
            if len(parts) >= 3:
                upstream_match = re.match(r"\[([^\]]+)\]", parts[2])
                if upstream_match:
                    upstream = upstream_match.group(1).split(":")[0]
            branches.append(
                BranchEntry(name=name, sha=sha, is_current=is_current, upstream=upstream)
            )
    return branches


# --- Stash parsing ---


def parse_stash_list(output: str) -> int:
    """Parse git stash list and return count."""
    if not output.strip():
        return 0
    return len(output.strip().splitlines())


# --- Remote URL parsing ---


def parse_remote_url(url: str) -> tuple[str, str]:
    """Parse a remote URL into (platform, owner/repo).

    Returns ("github", "owner/repo") or ("gitlab", "owner/repo") or ("unknown", url).
    """
    url = url.strip()

    # SSH: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
        platform = _host_to_platform(host)
        return platform, path

    # HTTPS: https://github.com/owner/repo.git
    https_match = re.match(r"https?://([^/]+)/(.+?)(?:\.git)?$", url)
    if https_match:
        host = https_match.group(1)
        path = https_match.group(2)
        platform = _host_to_platform(host)
        return platform, path

    return "unknown", url


@dataclass
class WorktreeEntry:
    """A git worktree entry."""

    path: str
    head: str
    branch: str  # branch name or "(detached)"
    is_bare: bool = False
    prunable: bool = False


def parse_worktree_list(output: str) -> list[WorktreeEntry]:
    """Parse git worktree list --porcelain output."""
    entries: list[WorktreeEntry] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line:
            # Blank line separates entries
            if current:
                entries.append(_build_worktree_entry(current))
                current = {}
        elif line.startswith("worktree "):
            current["path"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            # refs/heads/feature -> feature
            ref = line[len("branch "):]
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "bare":
            current["bare"] = "true"
        elif line == "detached":
            current["detached"] = "true"
        elif line == "prunable":
            current["prunable"] = "true"

    # Last entry (no trailing blank line)
    if current:
        entries.append(_build_worktree_entry(current))

    return entries


def _build_worktree_entry(data: dict[str, str]) -> WorktreeEntry:
    branch = data.get("branch", "")
    if data.get("detached"):
        branch = "(detached)"
    return WorktreeEntry(
        path=data.get("path", ""),
        head=data.get("head", ""),
        branch=branch,
        is_bare=data.get("bare") == "true",
        prunable=data.get("prunable") == "true",
    )


def _host_to_platform(host: str) -> str:
    if "github" in host:
        return "github"
    elif "gitlab" in host:
        return "gitlab"
    return "unknown"
