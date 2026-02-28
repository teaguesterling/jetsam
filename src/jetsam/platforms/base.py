"""Abstract platform interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
    labels: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    """CI check result."""

    name: str
    status: str  # "pass", "fail", "pending", "neutral"
    url: str = ""


class Platform(ABC):
    """Abstract interface for GitHub/GitLab operations."""

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
