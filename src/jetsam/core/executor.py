"""Plan execution with step-by-step results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jetsam.core.planner import Plan, PlanStep
from jetsam.core.state import build_state
from jetsam.git.wrapper import run_git_sync


@dataclass
class StepResult:
    """Result of executing a single plan step."""

    step: str
    ok: bool
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"step": self.step, "ok": self.ok}
        if self.error:
            d["error"] = self.error
        d.update(self.details)
        return d


@dataclass
class ExecutionResult:
    """Result of executing a full plan."""

    plan_id: str
    status: str  # "ok", "partial", "failed"
    results: list[StepResult]

    @property
    def completed_steps(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def total_steps(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "plan_id": self.plan_id,
            "status": self.status,
            "results": [r.to_dict() for r in self.results],
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
        }
        if self.status == "partial":
            d["rollback_hint"] = self._rollback_hint()
        return d

    def _rollback_hint(self) -> str:
        # Check what was completed
        committed = any(r.step == "commit" and r.ok for r in self.results)
        pushed = any(r.step == "push" and r.ok for r in self.results)
        if committed and not pushed:
            sha = ""
            for r in self.results:
                if r.step == "commit" and r.ok:
                    sha = r.details.get("sha", "")
            return f"Commit {sha} is local-only. Safe to amend or reset."
        if pushed:
            return "Changes were pushed. Consider reverting with a new commit."
        return "No persistent changes were made."


def execute_plan(plan: Plan, cwd: str | None = None) -> ExecutionResult:
    """Execute a plan step by step.

    Validates state hash before executing. Stops on first failure.
    """
    # Validate state hasn't changed
    current_state = build_state(cwd=cwd)
    current_hash = current_state.compute_hash(scope=plan.scope)
    if current_hash != plan.state_hash:
        return ExecutionResult(
            plan_id=plan.plan_id,
            status="failed",
            results=[
                StepResult(
                    step="validate",
                    ok=False,
                    error="stale_plan",
                    details={
                        "message": "Repository state changed since plan was created.",
                        "expected_hash": plan.state_hash,
                        "current_hash": current_hash,
                    },
                )
            ],
        )

    results: list[StepResult] = []
    for step in plan.steps:
        result = _execute_step(step, cwd=cwd)
        results.append(result)
        if not result.ok:
            return ExecutionResult(
                plan_id=plan.plan_id,
                status="partial" if results else "failed",
                results=results,
            )

    return ExecutionResult(
        plan_id=plan.plan_id,
        status="ok",
        results=results,
    )


def _execute_step(step: PlanStep, cwd: str | None = None) -> StepResult:
    """Execute a single plan step."""
    executor = _STEP_EXECUTORS.get(step.action)
    if executor is None:
        return StepResult(
            step=step.action,
            ok=False,
            error=f"Unknown step action: {step.action}",
        )
    return executor(step, cwd)


def _exec_stage(step: PlanStep, cwd: str | None) -> StepResult:
    files = step.params.get("files", [])
    if not files:
        return StepResult(step="stage", ok=True, details={"files": 0})

    result = run_git_sync(["add", "--", *files], cwd=cwd)
    if result.ok:
        return StepResult(step="stage", ok=True, details={"files": len(files)})
    return StepResult(step="stage", ok=False, error=result.stderr.strip())


def _exec_commit(step: PlanStep, cwd: str | None) -> StepResult:
    message = step.params.get("message", "update")
    result = run_git_sync(["commit", "-m", message], cwd=cwd)
    if result.ok:
        # Extract SHA from output
        sha = ""
        for line in result.stdout.splitlines():
            if line.startswith("["):
                parts = line.split()
                for p in parts:
                    if len(p) >= 7 and p.rstrip("]").replace("-", "").isalnum():
                        sha = p.rstrip("]")
                        break
        return StepResult(step="commit", ok=True, details={"sha": sha, "message": message})
    return StepResult(step="commit", ok=False, error=result.stderr.strip())


def _exec_push(step: PlanStep, cwd: str | None) -> StepResult:
    branch = step.params.get("branch", "")
    remote = step.params.get("remote", "origin")
    args = ["push"]
    if step.params.get("set_upstream"):
        args.extend(["-u", remote, branch])
    else:
        args.extend([remote, branch])

    result = run_git_sync(args, cwd=cwd)
    if result.ok:
        return StepResult(step="push", ok=True, details={"branch": branch, "remote": remote})
    return StepResult(
        step="push",
        ok=False,
        error=result.stderr.strip(),
        details={"recoverable": "rejected" in result.stderr.lower()},
    )


def _exec_fetch(step: PlanStep, cwd: str | None) -> StepResult:
    remote = step.params.get("remote", "origin")
    result = run_git_sync(["fetch", remote], cwd=cwd)
    if result.ok:
        return StepResult(step="fetch", ok=True)
    return StepResult(step="fetch", ok=False, error=result.stderr.strip())


def _exec_rebase(step: PlanStep, cwd: str | None) -> StepResult:
    onto = step.params.get("onto", "")
    result = run_git_sync(["rebase", onto], cwd=cwd)
    if result.ok:
        return StepResult(step="rebase", ok=True, details={"onto": onto})
    return StepResult(step="rebase", ok=False, error=result.stderr.strip())


def _exec_merge(step: PlanStep, cwd: str | None) -> StepResult:
    from_ref = step.params.get("from", "")
    result = run_git_sync(["merge", from_ref], cwd=cwd)
    if result.ok:
        return StepResult(step="merge", ok=True, details={"from": from_ref})
    return StepResult(step="merge", ok=False, error=result.stderr.strip())


def _exec_stash(step: PlanStep, cwd: str | None) -> StepResult:
    message = step.params.get("message", "")
    args = ["stash", "push"]
    if message:
        args.extend(["-m", message])
    result = run_git_sync(args, cwd=cwd)
    if result.ok:
        return StepResult(step="stash", ok=True)
    return StepResult(step="stash", ok=False, error=result.stderr.strip())


def _exec_stash_pop(step: PlanStep, cwd: str | None) -> StepResult:
    result = run_git_sync(["stash", "pop"], cwd=cwd)
    if result.ok:
        return StepResult(step="stash_pop", ok=True)
    return StepResult(step="stash_pop", ok=False, error=result.stderr.strip())


def _get_platform(cwd: str | None) -> Any:
    """Lazily resolve the platform adapter."""
    from jetsam.core.state import build_state
    from jetsam.platforms.github import GitHubPlatform

    state = build_state(cwd=cwd)
    if state.platform == "github":
        return GitHubPlatform(cwd=cwd)
    # GitLab support is Phase 3
    return None


def _exec_pr_create(step: PlanStep, cwd: str | None) -> StepResult:
    platform = _get_platform(cwd)
    if platform is None:
        return StepResult(step="pr_create", ok=False, error="No platform configured")

    title = step.params.get("title", "")
    base = step.params.get("base", "main")
    body = step.params.get("body", "")
    draft = step.params.get("draft", False)

    try:
        pr = platform.pr_create(title=title, body=body, base=base, draft=draft)
        return StepResult(
            step="pr_create",
            ok=True,
            details={"number": pr.number, "url": pr.url, "title": pr.title},
        )
    except Exception as e:
        return StepResult(step="pr_create", ok=False, error=str(e))


def _exec_pr_update(step: PlanStep, cwd: str | None) -> StepResult:
    # PR update is a no-op for now — pushing to the branch updates the PR
    number = step.params.get("number", 0)
    return StepResult(
        step="pr_update", ok=True, details={"number": number, "note": "PR updated via push"},
    )


def _exec_pr_merge(step: PlanStep, cwd: str | None) -> StepResult:
    platform = _get_platform(cwd)
    if platform is None:
        return StepResult(step="pr_merge", ok=False, error="No platform configured")

    strategy = step.params.get("strategy", "squash")
    # Need to find the PR number — get it from the current branch
    from jetsam.core.state import build_state

    state = build_state(cwd=cwd)
    pr = platform.pr_for_branch(state.branch)
    if pr is None:
        return StepResult(step="pr_merge", ok=False, error="No PR found for current branch")

    ok = platform.pr_merge(pr.number, strategy=strategy)
    if ok:
        return StepResult(
            step="pr_merge", ok=True, details={"number": pr.number, "strategy": strategy},
        )
    return StepResult(step="pr_merge", ok=False, error="Merge failed")


def _exec_checkout(step: PlanStep, cwd: str | None) -> StepResult:
    branch = step.params.get("branch", "")
    create = step.params.get("create", False)
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch)

    result = run_git_sync(args, cwd=cwd)
    if result.ok:
        return StepResult(step="checkout", ok=True, details={"branch": branch})
    return StepResult(step="checkout", ok=False, error=result.stderr.strip())


_STEP_EXECUTORS = {
    "stage": _exec_stage,
    "commit": _exec_commit,
    "push": _exec_push,
    "fetch": _exec_fetch,
    "rebase": _exec_rebase,
    "merge": _exec_merge,
    "stash": _exec_stash,
    "stash_pop": _exec_stash_pop,
    "pr_create": _exec_pr_create,
    "pr_update": _exec_pr_update,
    "pr_merge": _exec_pr_merge,
    "checkout": _exec_checkout,
}
