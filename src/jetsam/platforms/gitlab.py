"""GitLab platform adapter using glab CLI."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from jetsam.platforms.base import CheckResult, IssueDetails, Platform, PRDetails


class GitLabPlatform(Platform):
    """GitLab platform operations via glab CLI."""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd

    def _run_glab(self, args: list[str]) -> tuple[bool, str, str]:
        """Run a glab command. Returns (ok, stdout, stderr)."""
        cmd = ["glab", *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.cwd,
            )
            return proc.returncode == 0, proc.stdout, proc.stderr
        except FileNotFoundError:
            return False, "", "glab: command not found. Install with: https://gitlab.com/gitlab-org/cli"

    def _run_glab_json(self, args: list[str]) -> tuple[bool, Any]:
        """Run a glab command and parse JSON output."""
        ok, stdout, stderr = self._run_glab(args)
        if not ok:
            return False, stderr
        try:
            return True, json.loads(stdout)
        except json.JSONDecodeError:
            return False, f"Failed to parse glab output: {stdout[:200]}"

    def is_available(self) -> bool:
        """Check if glab is installed and authenticated."""
        ok, _, _ = self._run_glab(["auth", "status"])
        return ok

    def pr_for_branch(self, branch: str) -> PRDetails | None:
        """Get the MR for a branch."""
        ok, data = self._run_glab_json([
            "mr", "view", branch,
            "--output", "json",
        ])
        if not ok:
            return None
        return _parse_mr(data)

    def pr_create(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> PRDetails:
        """Create a new merge request."""
        args = ["mr", "create", "--title", title, "--target-branch", base]
        if body:
            args.extend(["--description", body])
        else:
            args.extend(["--description", ""])
        if draft:
            args.append("--draft")
        args.extend(["--no-editor"])

        ok, stdout, stderr = self._run_glab(args)
        if not ok:
            raise PlatformError(f"Failed to create MR: {stderr.strip()}")

        url = stdout.strip()
        # Try to fetch MR details
        ok2, data = self._run_glab_json(["mr", "view", url, "--output", "json"])
        if ok2:
            return _parse_mr(data)

        return PRDetails(
            number=0, state="open", title=title, url=url, base=base, draft=draft,
        )

    def pr_list(
        self,
        state: str = "open",
        author: str | None = None,
    ) -> list[PRDetails]:
        """List merge requests."""
        # glab uses "opened" instead of "open"
        glab_state = "opened" if state == "open" else state
        args = [
            "mr", "list",
            "--state", glab_state,
            "--output", "json",
            "--per-page", "50",
        ]
        if author:
            args.extend(["--author", author])

        ok, data = self._run_glab_json(args)
        if not ok:
            return []

        if isinstance(data, list):
            return [_parse_mr(item) for item in data]
        return []

    def pr_checks(self, pr_number: int) -> list[CheckResult]:
        """Get pipeline status for an MR."""
        ok, data = self._run_glab_json([
            "mr", "view", str(mr_number_to_iid(pr_number)),
            "--output", "json",
        ])
        if not ok:
            return []

        # Extract pipeline info from MR data
        pipeline = data.get("pipeline", {}) if isinstance(data, dict) else {}
        if not pipeline:
            return []

        status = _normalize_pipeline_status(pipeline.get("status", ""))
        return [CheckResult(
            name="pipeline",
            status=status,
            url=pipeline.get("web_url", ""),
        )]

    def pr_merge(
        self,
        pr_number: int,
        strategy: str = "squash",
        delete_branch: bool = True,
    ) -> bool:
        """Merge an MR."""
        args = ["mr", "merge", str(pr_number)]
        if strategy == "squash":
            args.append("--squash")
        if delete_branch:
            args.append("--remove-source-branch")
        args.append("--yes")

        ok, _, _ = self._run_glab(args)
        return ok

    def issue_list(
        self,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[IssueDetails]:
        """List issues."""
        glab_state = "opened" if state == "open" else state
        args = [
            "issue", "list",
            "--state", glab_state,
            "--output", "json",
            "--per-page", "50",
        ]
        if labels:
            args.extend(["--label", ",".join(labels)])

        ok, data = self._run_glab_json(args)
        if not ok:
            return []

        if isinstance(data, list):
            return [_parse_gl_issue(item) for item in data]
        return []

    def issue_get(self, number: int) -> IssueDetails | None:
        """Get issue details by number."""
        ok, data = self._run_glab_json([
            "issue", "view", str(number),
            "--output", "json",
        ])
        if not ok:
            return None
        return _parse_gl_issue(data)


def mr_number_to_iid(number: int) -> int:
    """GitLab uses iid (project-scoped) for MR references. glab accepts iid directly."""
    return number


def _parse_mr(data: dict[str, Any]) -> PRDetails:
    """Parse glab JSON output into PRDetails."""
    labels = data.get("labels", [])
    if not isinstance(labels, list):
        labels = []

    # glab uses "iid" for project-scoped number
    number = data.get("iid", data.get("number", 0))

    # Map GitLab MR state to our standard
    state = data.get("state", "opened").lower()
    if state == "opened":
        state = "open"

    return PRDetails(
        number=number,
        state=state,
        title=data.get("title", ""),
        body=data.get("description", ""),
        url=data.get("web_url", ""),
        base=data.get("target_branch", ""),
        head=data.get("source_branch", ""),
        draft=data.get("draft", False) or data.get("work_in_progress", False),
        labels=[str(lb) for lb in labels],
    )


def _parse_gl_issue(data: dict[str, Any]) -> IssueDetails:
    """Parse glab issue JSON output into IssueDetails."""
    labels = data.get("labels", [])
    if not isinstance(labels, list):
        labels = []

    assignees = []
    raw_assignees = data.get("assignees", [])
    if isinstance(raw_assignees, list):
        assignees = [
            a.get("username", "") if isinstance(a, dict) else str(a) for a in raw_assignees
        ]

    state = data.get("state", "opened").lower()
    if state == "opened":
        state = "open"

    return IssueDetails(
        number=data.get("iid", data.get("number", 0)),
        title=data.get("title", ""),
        state=state,
        body=data.get("description", ""),
        url=data.get("web_url", ""),
        labels=[str(lb) for lb in labels],
        assignees=assignees,
    )


def _normalize_pipeline_status(status: str) -> str:
    """Normalize GitLab pipeline status to our standard."""
    status = status.lower()
    if status in ("success", "passed"):
        return "pass"
    if status in ("failed", "canceled"):
        return "fail"
    if status in ("pending", "running", "created", "waiting_for_resource", "preparing"):
        return "pending"
    return "neutral"


class PlatformError(Exception):
    """Raised when a platform operation fails."""
