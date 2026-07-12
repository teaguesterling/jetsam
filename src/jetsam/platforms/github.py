"""GitHub platform adapter using gh CLI."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from jetsam.platforms.base import (
    MERGE_STRATEGIES,
    REVIEW_EVENTS,
    CheckResult,
    IssueDetails,
    Platform,
    PlatformError,
    PRDetails,
)


class GitHubPlatform(Platform):
    """GitHub platform operations via gh CLI."""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd

    def _run_gh(self, args: list[str]) -> tuple[bool, str, str]:
        """Run a gh command. Returns (ok, stdout, stderr)."""
        cmd = ["gh", *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )
            return proc.returncode == 0, proc.stdout, proc.stderr
        except FileNotFoundError:
            return False, "", "gh: command not found. Install with: https://cli.github.com/"

    def _run_gh_json(self, args: list[str]) -> tuple[bool, Any]:
        """Run a gh command and parse JSON output."""
        ok, stdout, stderr = self._run_gh(args)
        if not ok:
            return False, stderr
        try:
            return True, json.loads(stdout)
        except json.JSONDecodeError:
            return False, f"Failed to parse gh output: {stdout[:200]}"

    def pr_for_branch(self, branch: str) -> PRDetails | None:
        """Get the PR for a branch."""
        ok, data = self._run_gh_json([
            "pr", "view", branch,
            "--json",
            "number,state,title,body,url,baseRefName,headRefName,isDraft,labels,mergeable",
        ])
        if not ok:
            return None
        return _parse_pr(data)

    def pr_create(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> PRDetails:
        """Create a new PR."""
        args = ["pr", "create", "--title", title, "--base", base]
        if body:
            args.extend(["--body", body])
        else:
            args.extend(["--body", ""])
        if draft:
            args.append("--draft")

        ok, stdout, stderr = self._run_gh(args)
        if not ok:
            raise PlatformError(f"Failed to create PR: {stderr.strip()}")

        # gh pr create outputs the URL on success
        url = stdout.strip()

        # Fetch the PR details
        ok2, data = self._run_gh_json([
            "pr", "view", url,
            "--json",
            "number,state,title,body,url,baseRefName,headRefName,isDraft,labels,mergeable",
        ])
        if ok2:
            return _parse_pr(data)

        # Fallback: construct from what we know
        return PRDetails(
            number=0, state="open", title=title, url=url, base=base, draft=draft,
        )

    def pr_list(
        self,
        state: str = "open",
        author: str | None = None,
    ) -> list[PRDetails]:
        """List PRs."""
        args = [
            "pr", "list",
            "--state", state,
            "--json", "number,state,title,url,baseRefName,headRefName,isDraft,labels,mergeable",
            "--limit", "50",
        ]
        if author:
            args.extend(["--author", author])

        ok, data = self._run_gh_json(args)
        if not ok:
            return []

        if isinstance(data, list):
            return [_parse_pr(item) for item in data]
        return []

    def pr_checks(self, pr_number: int) -> list[CheckResult]:
        """Get check results for a PR."""
        ok, data = self._run_gh_json([
            "pr", "checks", str(pr_number),
            "--json", "name,state,detailsUrl",
        ])
        if not ok:
            return []

        results: list[CheckResult] = []
        if isinstance(data, list):
            for item in data:
                results.append(CheckResult.from_fields(
                    name=item.get("name", ""),
                    status=_normalize_check_status(item.get("state", "")),
                    url=item.get("detailsUrl", ""),
                ))
        return results

    def pr_merge(
        self,
        pr_number: int,
        strategy: str = "squash",
        delete_branch: bool = True,
    ) -> bool:
        """Merge a PR."""
        if strategy not in MERGE_STRATEGIES:
            raise ValueError(
                f"invalid merge strategy {strategy!r}; expected one of {MERGE_STRATEGIES}"
            )
        args = ["pr", "merge", str(pr_number), f"--{strategy}"]
        if delete_branch:
            args.append("--delete-branch")

        ok, _, _ = self._run_gh(args)
        return ok

    def release_create(
        self,
        tag: str,
        title: str,
        notes: str = "",
        draft: bool = False,
    ) -> dict[str, str]:
        """Create a GitHub release."""
        args = ["release", "create", tag, "--title", title]
        if notes:
            args.extend(["--notes", notes])
        else:
            args.extend(["--notes", ""])
        if draft:
            args.append("--draft")

        ok, stdout, stderr = self._run_gh(args)
        if not ok:
            raise PlatformError(f"Failed to create release: {stderr.strip()}")

        url = stdout.strip()
        return {"tag": tag, "url": url}

    def issue_list(
        self,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[IssueDetails]:
        """List issues."""
        args = [
            "issue", "list",
            "--state", state,
            "--json", "number,title,state,body,url,labels,assignees",
            "--limit", "50",
        ]
        if labels:
            args.extend(["--label", ",".join(labels)])

        ok, data = self._run_gh_json(args)
        if not ok:
            return []

        if isinstance(data, list):
            return [_parse_issue(item) for item in data]
        return []

    def issue_get(self, number: int) -> IssueDetails | None:
        """Get issue details by number."""
        ok, data = self._run_gh_json([
            "issue", "view", str(number),
            "--json", "number,title,state,body,url,labels,assignees",
        ])
        if not ok:
            return None
        return _parse_issue(data)

    def pr_comment(self, pr_number: int, body: str) -> dict[str, str]:
        """Post a comment on a PR."""
        ok, stdout, stderr = self._run_gh([
            "pr", "comment", str(pr_number), "--body", body,
        ])
        if not ok:
            raise PlatformError(f"Failed to comment on PR #{pr_number}: {stderr.strip()}")
        return {"number": str(pr_number), "url": stdout.strip()}

    def pr_review(self, pr_number: int, body: str, event: str) -> dict[str, str]:
        """Submit a PR review."""
        if event not in REVIEW_EVENTS:
            raise ValueError(
                f"invalid review event {event!r}; expected one of {REVIEW_EVENTS}"
            )
        args = ["pr", "review", str(pr_number), f"--{event}"]
        if body:
            args.extend(["--body", body])
        ok, stdout, stderr = self._run_gh(args)
        if not ok:
            raise PlatformError(f"Failed to review PR #{pr_number}: {stderr.strip()}")
        return {"number": str(pr_number), "event": event, "url": stdout.strip()}

    def pr_comments(self, pr_number: int) -> list[dict[str, str]]:
        """Read comments and reviews on a PR."""
        comments: list[dict[str, str]] = []

        # Issue comments (regular comments)
        ok, data = self._run_gh_json([
            "api", f"repos/{{owner}}/{{repo}}/issues/{pr_number}/comments",
        ])
        if ok and isinstance(data, list):
            for item in data:
                user = item.get("user", {})
                comments.append({
                    "author": user.get("login", "") if isinstance(user, dict) else "",
                    "body": item.get("body", ""),
                    "created_at": item.get("created_at", ""),
                    "type": "comment",
                })

        # Review comments
        ok2, data2 = self._run_gh_json([
            "api", f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/reviews",
        ])
        if ok2 and isinstance(data2, list):
            for item in data2:
                user = item.get("user", {})
                comments.append({
                    "author": user.get("login", "") if isinstance(user, dict) else "",
                    "body": item.get("body", ""),
                    "created_at": item.get("submitted_at", ""),
                    "type": "review",
                })

        comments.sort(key=lambda c: c.get("created_at", ""))
        return comments

    def issue_close(
        self, number: int, comment: str | None = None, reason: str = "completed"
    ) -> dict[str, str]:
        """Close an issue, optionally with a comment."""
        if comment:
            ok, _, stderr = self._run_gh(["issue", "comment", str(number), "--body", comment])
            if not ok:
                raise PlatformError(f"Failed to comment on issue #{number}: {stderr.strip()}")

        args = ["issue", "close", str(number), "--reason", reason]
        ok, _, stderr = self._run_gh(args)
        if not ok:
            raise PlatformError(f"Failed to close issue #{number}: {stderr.strip()}")

        return {"number": str(number), "state": "closed", "reason": reason}

    def is_available(self) -> bool:
        """Check if gh is installed and authenticated."""
        ok, _, _ = self._run_gh(["auth", "status"])
        return ok


def _parse_issue(data: dict[str, Any]) -> IssueDetails:
    """Parse gh JSON output into IssueDetails."""
    labels = []
    raw_labels = data.get("labels", [])
    if isinstance(raw_labels, list):
        labels = [lb.get("name", "") if isinstance(lb, dict) else str(lb) for lb in raw_labels]

    assignees = []
    raw_assignees = data.get("assignees", [])
    if isinstance(raw_assignees, list):
        assignees = [
            a.get("login", "") if isinstance(a, dict) else str(a) for a in raw_assignees
        ]

    return IssueDetails.from_fields(
        number=data.get("number", 0),
        title=data.get("title", ""),
        state=data.get("state", "open").lower(),
        body=data.get("body", ""),
        url=data.get("url", ""),
        labels=labels,
        assignees=assignees,
    )


def _parse_pr(data: dict[str, Any]) -> PRDetails:
    """Parse gh JSON output into PRDetails."""
    labels = []
    raw_labels = data.get("labels", [])
    if isinstance(raw_labels, list):
        labels = [lb.get("name", "") if isinstance(lb, dict) else str(lb) for lb in raw_labels]

    # gh reports mergeability as MERGEABLE / CONFLICTING / UNKNOWN, where
    # UNKNOWN usually means GitHub is still computing it — keep the raw
    # tri-state so callers can tell "conflicting" from "not computed yet".
    raw_mergeable = str(data.get("mergeable") or "").lower()

    # from_fields drops any field the loaded PRDetails doesn't declare, so a
    # newer parser never crashes an older (already-imported) model — see
    # FieldTolerant in base.py.
    return PRDetails.from_fields(
        number=data.get("number", 0),
        state=data.get("state", "open").lower(),
        title=data.get("title", ""),
        body=data.get("body", ""),
        url=data.get("url", ""),
        base=data.get("baseRefName", ""),
        head=data.get("headRefName", ""),
        draft=data.get("isDraft", False),
        mergeable=raw_mergeable == "mergeable",
        mergeable_state=raw_mergeable or "unknown",
        labels=labels,
    )


def _normalize_check_status(status: str) -> str:
    """Normalize gh check status to our standard."""
    status = status.lower()
    if status in ("success", "pass"):
        return "pass"
    if status in ("failure", "fail", "error"):
        return "fail"
    if status in ("pending", "queued", "in_progress", "waiting"):
        return "pending"
    return "neutral"


