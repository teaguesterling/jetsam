"""MCP tool definitions mapping to core operations."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jetsam.platforms.base import Platform

from mcp.server.fastmcp import FastMCP

from jetsam.config.manager import load_config
from jetsam.core.executor import execute_plan
from jetsam.core.output import JetsamError
from jetsam.core.planner import (
    plan_finish,
    plan_release,
    plan_save,
    plan_ship,
    plan_start,
    plan_switch,
    plan_sync,
    plan_tidy,
)
from jetsam.core.plans import PlanStore, generate_plan_id, update_plan
from jetsam.core.state import build_state
from jetsam.git.parsers import parse_diff_numstat, parse_log
from jetsam.git.wrapper import run_git_sync

_plan_store: PlanStore | None = None


def _get_platform(state: Any) -> Platform | None:
    """Resolve the platform adapter from state."""
    from jetsam.platforms import get_platform
    return get_platform(state.platform, cwd=state.repo_root)


def _get_store() -> PlanStore:
    global _plan_store
    if _plan_store is None:
        state = build_state()
        _plan_store = PlanStore(state.repo_root)
        _plan_store.cleanup_expired()
    return _plan_store


def _no_platform_error() -> dict[str, Any]:
    """Standard error for missing platform configuration."""
    return JetsamError(
        error="no_platform",
        message="No platform configured.",
        suggested_action="Configure a GitHub or GitLab remote.",
        recoverable=False,
    ).to_dict()


def _no_pr_error(branch: str) -> dict[str, Any]:
    """Standard error for missing PR."""
    return JetsamError(
        error="no_pr",
        message=f"No PR found for branch '{branch}'.",
        recoverable=True,
    ).to_dict()


def register_tools(mcp: FastMCP) -> None:
    """Register all jetsam tools with the MCP server."""

    @mcp.tool()
    def status(cwd: str | None = None) -> dict[str, Any]:
        """Get repository state snapshot.

        Returns branch, dirty state, staged/unstaged/untracked files,
        ahead/behind counts, platform info, and PR details if available.
        """
        state = build_state(cwd=cwd)
        return state.to_dict()

    @mcp.tool()
    def save(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        files: list[str] | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Stage and commit changes. Returns a plan to confirm().

        Args:
            message: Commit message. Auto-generated if omitted.
            include: Glob pattern to filter files to stage.
            exclude: Glob pattern to filter files out.
            files: Explicit file paths to stage.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        config = load_config(state.repo_root)
        pid = generate_plan_id()
        plan = plan_save(
            state, plan_id=pid,
            message=message, include=include, exclude=exclude, files=files,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def sync(strategy: str | None = None, cwd: str | None = None) -> dict[str, Any]:
        """Fetch, rebase/merge, and push. Returns a plan to confirm().

        Args:
            strategy: "rebase" or "merge". Defaults to rebase on feature
                     branches, merge on default branch.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        pid = generate_plan_id()
        plan = plan_sync(state, plan_id=pid, strategy=strategy)
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def ship(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        files: list[str] | None = None,
        to: str | None = None,
        pr: bool | None = None,
        merge: bool | None = None,
        draft: bool | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: stage, commit, push, open PR. Returns a plan.

        Args:
            message: Commit message and PR title.
            include: Glob pattern to filter files to stage.
            exclude: Glob pattern to filter files out.
            files: Explicit file paths to stage.
            to: Target branch for PR (default: main/master).
            pr: Create/update a PR. Defaults to config value or true.
            merge: Also merge the PR after creating it. Defaults to config value or false.
            draft: Create the PR as a draft. Defaults to config value or false.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        config = load_config(state.repo_root)
        pid = generate_plan_id()
        plan = plan_ship(
            state, plan_id=pid,
            message=message, include=include, exclude=exclude,
            files=files, to=to, open_pr=pr, merge=merge, draft=draft,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def log(
        n: int = 10, branch: str | None = None, cwd: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Condensed commit history.

        Args:
            n: Number of commits (default: 10).
            branch: Branch to show (default: current).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        fmt = "%H%x00%h%x00%an%x00%aI%x00%s"
        args = ["log", f"--format={fmt}", f"-{n}"]
        if branch:
            args.append(branch)

        result = run_git_sync(args, cwd=cwd)
        if not result.ok:
            return JetsamError(
                error="git_error",
                message=result.stderr.strip(),
                recoverable=True,
            ).to_dict()

        entries = parse_log(result.stdout)
        return [asdict(e) for e in entries]

    @mcp.tool()
    def diff(
        target: str | None = None,
        stat: bool = True,
        staged: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Show diff. Returns stat summary by default, full diff if stat=false.

        Args:
            target: Diff target ref (default: working tree changes).
            stat: Return stat summary instead of full diff (default: true).
            staged: Diff staged changes instead of unstaged.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        if stat:
            args = ["diff", "--numstat"]
            if staged:
                args.append("--cached")
            if target:
                args.append(target)

            result = run_git_sync(args, cwd=cwd)
            if not result.ok:
                return JetsamError(
                    error="git_error",
                    message=result.stderr.strip(),
                    recoverable=True,
                ).to_dict()

            parsed = parse_diff_numstat(result.stdout)
            return asdict(parsed)
        else:
            args = ["diff"]
            if staged:
                args.append("--cached")
            if target:
                args.append(target)

            result = run_git_sync(args, cwd=cwd)
            if not result.ok:
                return JetsamError(
                    error="git_error",
                    message=result.stderr.strip(),
                    recoverable=True,
                ).to_dict()
            return {"diff": result.stdout, "ok": result.ok}

    @mcp.tool()
    def switch(branch: str, create: bool = False, cwd: str | None = None) -> dict[str, Any]:
        """Switch branches with automatic stash/unstash. Returns a plan.

        Args:
            branch: Target branch to switch to.
            create: Create the branch if it doesn't exist.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        pid = generate_plan_id()
        plan = plan_switch(state, plan_id=pid, branch=branch, create=create)
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def pr_view(branch: str | None = None, cwd: str | None = None) -> dict[str, Any]:
        """Get PR details for a branch.

        Args:
            branch: Branch to check (default: current branch).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        actual_branch = branch or state.branch
        platform = _get_platform(state)
        if platform is None:
            return _no_platform_error()
        pr = platform.pr_for_branch(actual_branch)
        if pr is None:
            return {"pr": None, "branch": actual_branch}
        return asdict(pr)

    @mcp.tool()
    def pr_list(
        state: str = "open",
        author: str | None = None,
        cwd: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """List pull requests.

        Args:
            state: Filter by state: open, closed, merged, all.
            author: Filter by author username.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()
        prs = platform.pr_list(state=state, author=author)
        return [asdict(p) for p in prs]

    @mcp.tool()
    def checks(
        pr_number: int | None = None, cwd: str | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """CI check status for current branch or a specific PR.

        Args:
            pr_number: PR number (default: PR for current branch).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()

        actual_pr = pr_number
        if actual_pr is None:
            pr = platform.pr_for_branch(repo_state.branch)
            if pr is None:
                return _no_pr_error(repo_state.branch)
            actual_pr = pr.number

        results = platform.pr_checks(actual_pr)
        return [asdict(c) for c in results]

    @mcp.tool()
    def start(
        target: str,
        worktree: bool | None = None,
        base: str | None = None,
        prefix: str | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Start work on an issue or feature. Returns a plan to confirm().

        Args:
            target: Issue number (e.g. "42") or branch name (e.g. "fix-parser").
            worktree: Create a worktree instead of switching branches.
            base: Base branch (default: main/master).
            prefix: Branch name prefix (e.g. "feature/").
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        config = load_config(state.repo_root)
        pid = generate_plan_id()

        # Fetch issue title if target is numeric
        issue_title = None
        if target.isdigit():
            platform = _get_platform(state)
            if platform:
                issue = platform.issue_get(int(target))
                if issue:
                    issue_title = issue.title

        plan = plan_start(
            state, plan_id=pid,
            target=target, issue_title=issue_title,
            branch_prefix=prefix, worktree=worktree, base=base,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def finish(
        strategy: str | None = None,
        no_delete: bool | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Merge PR and clean up branch. Returns a plan to confirm().

        Args:
            strategy: Merge strategy: "squash", "merge", or "rebase".
            no_delete: Keep the branch after merging.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        config = load_config(state.repo_root)
        pid = generate_plan_id()

        worktree_path = None
        if state.worktree and state.worktree.active:
            worktree_path = state.worktree.current

        plan = plan_finish(
            state, plan_id=pid,
            strategy=strategy, no_delete=no_delete,
            worktree_path=worktree_path,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def tidy(cwd: str | None = None) -> dict[str, Any]:
        """Prune merged branches and stale refs. Returns a plan to confirm()."""
        state = build_state(cwd=cwd)
        pid = generate_plan_id()
        plan = plan_tidy(state, plan_id=pid)
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def issues(
        state: str = "open",
        labels: list[str] | None = None,
        cwd: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """List issues from the project tracker.

        Args:
            state: Filter by state: open, closed, all.
            labels: Filter by labels.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()
        issue_list = platform.issue_list(state=state, labels=labels)
        return [asdict(i) for i in issue_list]

    @mcp.tool()
    def pr_comment(
        body: str,
        branch: str | None = None,
        pr_number: int | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Post a comment on a pull request.

        Args:
            body: Comment text.
            branch: Branch to find PR for (default: current branch).
            pr_number: PR number (overrides branch resolution).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()

        actual_pr = pr_number
        if actual_pr is None:
            actual_branch = branch or repo_state.branch
            pr = platform.pr_for_branch(actual_branch)
            if pr is None:
                return _no_pr_error(actual_branch)
            actual_pr = pr.number

        return platform.pr_comment(actual_pr, body)

    @mcp.tool()
    def pr_review(
        event: str,
        body: str = "",
        branch: str | None = None,
        pr_number: int | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Submit a PR review.

        Args:
            event: Review action: "approve", "request-changes", or "comment".
            body: Review body text. Required for request-changes and comment.
            branch: Branch to find PR for (default: current branch).
            pr_number: PR number (overrides branch resolution).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()

        actual_pr = pr_number
        if actual_pr is None:
            actual_branch = branch or repo_state.branch
            pr = platform.pr_for_branch(actual_branch)
            if pr is None:
                return _no_pr_error(actual_branch)
            actual_pr = pr.number

        return platform.pr_review(actual_pr, body, event)

    @mcp.tool()
    def pr_comments(
        branch: str | None = None,
        pr_number: int | None = None,
        cwd: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Read comments and reviews on a pull request.

        Args:
            branch: Branch to find PR for (default: current branch).
            pr_number: PR number (overrides branch resolution).
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()

        actual_pr = pr_number
        if actual_pr is None:
            actual_branch = branch or repo_state.branch
            pr = platform.pr_for_branch(actual_branch)
            if pr is None:
                return _no_pr_error(actual_branch)
            actual_pr = pr.number

        return platform.pr_comments(actual_pr)

    @mcp.tool()
    def issue_close(
        number: int,
        comment: str | None = None,
        reason: str = "completed",
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Close an issue, optionally with a comment.

        Args:
            number: Issue number.
            comment: Optional comment to post before closing.
            reason: Close reason: "completed" (default) or "not-planned".
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        repo_state = build_state(cwd=cwd)
        platform = _get_platform(repo_state)
        if platform is None:
            return _no_platform_error()

        return platform.issue_close(number, comment=comment, reason=reason)

    @mcp.tool()
    def release(
        tag: str,
        title: str | None = None,
        notes: str = "",
        draft: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Tag, push, and create a platform release. Returns a plan to confirm().

        Args:
            tag: Tag name (e.g. "v0.1.0").
            title: Release title (defaults to tag name).
            notes: Release notes text.
            draft: Create as a draft release.
            cwd: Working-directory override for this call. Defaults to
                the MCP server's cwd. Use to operate on a non-cwd repo without
                falling back to the `git` passthrough.
        """
        state = build_state(cwd=cwd)
        pid = generate_plan_id()
        plan = plan_release(
            state, plan_id=pid,
            tag=tag, title=title, notes=notes, draft=draft,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def show_plan(id: str) -> dict[str, Any]:
        """Show current state of a plan.

        Args:
            id: Plan ID returned by a workflow tool.
        """
        plan = _get_store().load(id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {id} not found or expired.",
                suggested_action="Re-run the original command.",
                recoverable=True,
            ).to_dict()
        return plan.to_dict()

    @mcp.tool()
    def modify_plan(
        id: str,
        message: str | None = None,
        exclude: str | None = None,
    ) -> dict[str, Any]:
        """Modify an existing plan before confirming.

        Args:
            id: Plan ID to modify.
            message: New commit message.
            exclude: Glob pattern for files to remove from staging.
        """
        plan = _get_store().load(id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {id} not found or expired.",
                suggested_action="Re-run the original command.",
                recoverable=True,
            ).to_dict()

        plan_diff = update_plan(plan, message=message, exclude=exclude)
        _get_store().save(plan)
        result = plan.to_dict()
        result["diff"] = plan_diff
        return result

    @mcp.tool()
    def confirm(id: str) -> dict[str, Any]:
        """Execute a plan. Validates repo state hasn't changed since planning.

        Args:
            id: Plan ID to execute.
        """
        store = _get_store()
        plan = store.load(id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {id} not found or expired.",
                suggested_action="Re-run the original command.",
                recoverable=True,
            ).to_dict()

        result = execute_plan(plan)
        store.delete(id)
        return result.to_dict()

    @mcp.tool()
    def cancel(id: str) -> dict[str, Any]:
        """Cancel a plan without executing.

        Args:
            id: Plan ID to cancel.
        """
        _get_store().delete(id)
        return {"ok": True, "id": id}

    @mcp.tool()
    def git(args: list[str]) -> dict[str, Any]:
        """Run any git command (pass-through).

        Args:
            args: Git arguments, e.g. ["rebase", "-i", "HEAD~3"].
        """
        result = run_git_sync(args)
        return {
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    @mcp.tool()
    def config(
        set: dict[str, Any] | None = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        """Read or update jetsam's in-memory session config.

        Returns the full current config dict. With `set=`, merges values
        and returns the new state. With `reset=true`, reverts to the
        env-seeded values captured at server launch. Wiped on server
        restart — no disk persistence.

        Keys:
            active_root         — fallback when a verb's cwd= is omitted
            log_level           — debug | info | warn | error
            default_sync_strategy — rebase | merge
            default_base_branch — override for "main"
            signing_required    — fail fast if GPG not configured
            auto_confirm_safe_verbs — verbs that bypass plan→confirm

        Env vars (seed at launch only): JETSAM_ACTIVE_ROOT,
        JETSAM_LOG_LEVEL, JETSAM_DEFAULT_SYNC_STRATEGY,
        JETSAM_DEFAULT_BASE_BRANCH, JETSAM_SIGNING_REQUIRED,
        JETSAM_AUTO_CONFIRM_SAFE_VERBS.

        Args:
            set: Dict of keys to update. Unknown keys raise; invalid
                values raise; either way the config is left unchanged.
            reset: If True, reset to env-seeded values (ignores `set`).
        """
        from jetsam.config.runtime import get_runtime, reset_runtime, update_runtime

        if reset:
            cfg = reset_runtime()
            return cfg.to_dict()

        if set:
            try:
                cfg = update_runtime(set)
            except ValueError as e:
                return JetsamError(
                    error="invalid_config",
                    message=str(e),
                    recoverable=True,
                ).to_dict()
            return cfg.to_dict()

        return get_runtime().to_dict()
