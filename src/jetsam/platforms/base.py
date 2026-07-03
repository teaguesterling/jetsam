"""Abstract platform interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Canonical allowlists for values interpolated into a ``gh``/``glab`` argv as
# ``--<value>`` flags. Single source of truth so the CLI (``click.Choice``) and
# the MCP path validate against the same set and cannot drift
# (GHSA-w893-5jfc-rwq9). An out-of-set value (e.g. "admin") must be rejected,
# never coerced, so an injection attempt surfaces rather than silently degrades.
MERGE_STRATEGIES: tuple[str, ...] = ("squash", "merge", "rebase")
REVIEW_EVENTS: tuple[str, ...] = ("approve", "request-changes", "comment")


@dataclass
class PRDetails:
    """Pull request / merge request details."""

    number: int
    state: str  # "open", "closed", "merged"
    title: str
    body: str = ""
    url: str = ""
    base: str = ""
    head: str = ""
    draft: bool = False
    checks: str = ""  # "passing", "failing", "pending", ""
    reviews: str = ""  # "approved", "changes_requested", ""
    mergeable: bool = False
    mergeable_state: str = "unknown"  # "mergeable", "conflicting", "unknown"
    labels: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    """CI check result."""

    name: str
    status: str  # "pass", "fail", "pending", "neutral"
    url: str = ""


@dataclass
class IssueDetails:
    """Issue details."""

    number: int
    title: str
    state: str  # "open", "closed"
    body: str = ""
    url: str = ""
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)


class Platform(ABC):
    """Abstract interface for GitHub/GitLab operations."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the platform CLI is installed and authenticated."""
        ...

    @abstractmethod
    def pr_for_branch(self, branch: str) -> PRDetails | None:
        """Get the PR for a branch, or None."""
        ...

    @abstractmethod
    def pr_create(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> PRDetails:
        """Create a new PR."""
        ...

    @abstractmethod
    def pr_list(
        self,
        state: str = "open",
        author: str | None = None,
    ) -> list[PRDetails]:
        """List PRs."""
        ...

    @abstractmethod
    def pr_checks(self, pr_number: int) -> list[CheckResult]:
        """Get check results for a PR."""
        ...

    @abstractmethod
    def pr_merge(
        self,
        pr_number: int,
        strategy: str = "squash",
        delete_branch: bool = True,
    ) -> bool:
        """Merge a PR. Returns True on success."""
        ...

    @abstractmethod
    def issue_list(
        self,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[IssueDetails]:
        """List issues."""
        ...

    @abstractmethod
    def release_create(
        self,
        tag: str,
        title: str,
        notes: str = "",
        draft: bool = False,
    ) -> dict[str, str]:
        """Create a release for a tag. Returns {"tag": ..., "url": ...}."""
        ...

    @abstractmethod
    def issue_get(self, number: int) -> IssueDetails | None:
        """Get issue details by number."""
        ...

    @abstractmethod
    def pr_comment(self, pr_number: int, body: str) -> dict[str, str]:
        """Post a comment on a PR. Returns {"number": ..., "url": ...}."""
        ...

    @abstractmethod
    def pr_review(self, pr_number: int, body: str, event: str) -> dict[str, str]:
        """Submit a PR review. event: 'approve', 'request-changes', 'comment'."""
        ...

    @abstractmethod
    def pr_comments(self, pr_number: int) -> list[dict[str, str]]:
        """Read comments on a PR. Returns [{author, body, created_at, type}]."""
        ...

    @abstractmethod
    def issue_close(
        self, number: int, comment: str | None = None, reason: str = "completed"
    ) -> dict[str, str]:
        """Close an issue. reason: 'completed' or 'not-planned'."""
        ...


class PlatformError(Exception):
    """Raised when a platform operation fails."""
