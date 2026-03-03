# P6-004: Thread State Through Executor

**Phase:** 6 — Config & Standardization
**Priority:** Medium impact, moderate effort
**Affects:** `src/jetsam/core/executor.py`

## Problem

`execute_plan()` calls `build_state()` at the top for hash validation (line 101),
but then several step executors call `build_state()` again internally:

- `_get_platform()` (line 250-256) — called by `_exec_pr_create`, `_exec_pr_merge`,
  `_exec_release_create`
- `_exec_pr_merge()` (line 299-301) — calls `build_state()` for branch lookup
- `_exec_worktree_add()` (line 337-339) — calls `build_state()` for repo_root

Each `build_state()` call runs 6-7 git subprocess commands (~50ms each). In a `ship`
plan with PR creation, this means 3 redundant state builds (~150ms wasted).

## Solution

Thread the initial `RepoState` through to step executors:

### Step 1: Change executor function signature

```python
# Step executor type
StepExecutor = Callable[[PlanStep, str | None, RepoState], StepResult]

def _execute_step(step: PlanStep, cwd: str | None, state: RepoState) -> StepResult:
    executor = _STEP_EXECUTORS.get(step.action)
    if executor is None:
        return StepResult(step=step.action, ok=False, error=f"Unknown: {step.action}")
    return executor(step, cwd, state)
```

### Step 2: Update all step executors

Most executors ignore the state parameter. Only the platform-related ones use it:

```python
def _exec_pr_create(step: PlanStep, cwd: str | None, state: RepoState) -> StepResult:
    platform = get_platform(state.platform, cwd=cwd)
    # ... rest unchanged
```

### Step 3: Remove redundant _get_platform() helper

The helper that calls `build_state()` internally becomes unnecessary.

## Acceptance Criteria

- [ ] `execute_plan()` passes the validated state to all step executors
- [ ] No step executor calls `build_state()` internally
- [ ] `_get_platform()` helper in executor.py removed or simplified
- [ ] All existing tests pass
- [ ] Measurable performance improvement on plans with platform steps

## Estimated Scope

~40 lines changed in `executor.py`. All executor function signatures gain a `state`
parameter, but most ignore it.

## Notes

This is a larger refactor touching every executor function signature. The `_STEP_EXECUTORS`
dict values need to match the new signature. Consider whether backward compatibility
matters (it shouldn't — these are all internal).
