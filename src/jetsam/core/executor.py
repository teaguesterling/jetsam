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


_STEP_EXECUTORS = {
    "stage": _exec_stage,
    "commit": _exec_commit,
    "push": _exec_push,
    "fetch": _exec_fetch,
    "rebase": _exec_rebase,
    "merge": _exec_merge,
    "stash": _exec_stash,
    "stash_pop": _exec_stash_pop,
}
