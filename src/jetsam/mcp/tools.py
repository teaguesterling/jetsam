"""MCP tool definitions mapping to core operations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from jetsam.core.executor import execute_plan
from jetsam.core.output import JetsamError
from jetsam.core.planner import plan_save, plan_ship, plan_sync
from jetsam.core.plans import PlanStore, generate_plan_id, update_plan
from jetsam.core.state import build_state
from jetsam.git.parsers import parse_diff_numstat, parse_log
from jetsam.git.wrapper import run_git_sync

# Module-level plan store (initialized lazily)
_plan_store: PlanStore | None = None


def _get_store() -> PlanStore:
    global _plan_store
    if _plan_store is None:
        state = build_state()
        _plan_store = PlanStore(state.repo_root)
    return _plan_store


def register_tools(mcp: FastMCP) -> None:
    """Register all jetsam tools with the MCP server."""

    @mcp.tool()
    def status() -> dict[str, Any]:
        """Get repository state snapshot.

        Returns branch, dirty state, staged/unstaged/untracked files,
        ahead/behind counts, platform info, and PR details if available.
        """
        state = build_state()
        return state.to_dict()

    @mcp.tool()
    def save(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Stage and commit changes. Returns a plan to be confirmed.

        Args:
            message: Commit message. Auto-generated if not provided.
            include: Glob pattern for files to include.
            exclude: Glob pattern for files to exclude.
            files: Explicit list of files to stage.
        """
        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_save(
            state, plan_id=plan_id,
            message=message, include=include, exclude=exclude, files=files,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def sync(strategy: str | None = None) -> dict[str, Any]:
        """Fetch, rebase/merge, and push. Returns a plan to be confirmed.

        Args:
            strategy: "rebase" or "merge". Default: rebase for feature branches,
                     merge for default branch.
        """
        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_sync(state, plan_id=plan_id, strategy=strategy)
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def ship(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        to: str | None = None,
        open_pr: bool = True,
        merge: bool = False,
    ) -> dict[str, Any]:
        """Full ship pipeline: stage, commit, push, PR. Returns a plan.

        Args:
            message: Commit message and PR title.
            include: Glob pattern for files to include.
            exclude: Glob pattern for files to exclude.
            to: Target branch for PR (default: main/master).
            open_pr: Whether to create/update a PR.
            merge: Whether to also merge the PR.
        """
        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_ship(
            state, plan_id=plan_id,
            message=message, include=include, exclude=exclude,
            to=to, open_pr=open_pr, merge=merge,
        )
        _get_store().save(plan)
        return plan.to_dict()

    @mcp.tool()
    def log(count: int = 10, branch: str | None = None) -> list[dict[str, Any]]:
        """Show condensed commit history.

        Args:
            count: Number of commits to show (default: 10).
            branch: Branch to show log for (default: current).
        """
        fmt = "%H%x00%h%x00%an%x00%aI%x00%s"
        args = ["log", f"--format={fmt}", f"-{count}"]
        if branch:
            args.append(branch)

        result = run_git_sync(args)
        if not result.ok:
            return [{"error": result.stderr.strip()}]

        from dataclasses import asdict
        entries = parse_log(result.stdout)
        return [asdict(e) for e in entries]

    @mcp.tool()
    def diff(
        target: str | None = None,
        stat_only: bool = True,
        staged: bool = False,
    ) -> dict[str, Any]:
        """Show diff with smart defaults.

        Args:
            target: Diff target (default: working tree changes).
            stat_only: Return only stat summary (default: true for structured).
            staged: Show staged changes instead of unstaged.
        """
        if stat_only:
            args = ["diff", "--numstat"]
            if staged:
                args.append("--cached")
            if target:
                args.append(target)

            result = run_git_sync(args)
            if not result.ok:
                return {"error": result.stderr.strip()}

            from dataclasses import asdict
            stat = parse_diff_numstat(result.stdout)
            return asdict(stat)
        else:
            args = ["diff"]
            if staged:
                args.append("--cached")
            if target:
                args.append(target)

            result = run_git_sync(args)
            return {"diff": result.stdout, "ok": result.ok}

    @mcp.tool()
    def show_plan(plan_id: str) -> dict[str, Any]:
        """Show the current state of a plan.

        Args:
            plan_id: The plan ID returned by a workflow tool.
        """
        plan = _get_store().load(plan_id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {plan_id} not found or expired. Re-plan required.",
                suggested_action="Re-run the original command to create a new plan.",
                recoverable=True,
            ).to_dict()
        return plan.to_dict()

    @mcp.tool()
    def modify_plan(
        plan_id: str,
        message: str | None = None,
        exclude: str | None = None,
    ) -> dict[str, Any]:
        """Modify an existing plan before confirming.

        Args:
            plan_id: The plan ID to modify.
            message: New commit message.
            exclude: Glob pattern for files to remove from staging.
        """
        plan = _get_store().load(plan_id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {plan_id} not found or expired.",
                recoverable=True,
            ).to_dict()

        diff = update_plan(plan, message=message, exclude=exclude)
        _get_store().save(plan)
        result = plan.to_dict()
        result["diff"] = diff
        return result

    @mcp.tool()
    def confirm(plan_id: str) -> dict[str, Any]:
        """Execute a plan. Validates state hasn't changed since planning.

        Args:
            plan_id: The plan ID to execute.
        """
        store = _get_store()
        plan = store.load(plan_id)
        if plan is None:
            return JetsamError(
                error="plan_not_found",
                message=f"Plan {plan_id} not found or expired.",
                suggested_action="Re-run the original command to create a new plan.",
                recoverable=True,
            ).to_dict()

        result = execute_plan(plan)
        store.delete(plan_id)
        return result.to_dict()

    @mcp.tool()
    def cancel_plan(plan_id: str) -> dict[str, Any]:
        """Cancel a plan without executing it.

        Args:
            plan_id: The plan ID to cancel.
        """
        _get_store().delete(plan_id)
        return {"ok": True, "plan_id": plan_id, "message": "Plan cancelled."}

    @mcp.tool()
    def git(args: list[str]) -> dict[str, Any]:
        """Run any git command (pass-through). Returns structured output.

        Args:
            args: Git command arguments (e.g., ["rebase", "-i", "HEAD~3"]).
        """
        result = run_git_sync(args)
        return {
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
