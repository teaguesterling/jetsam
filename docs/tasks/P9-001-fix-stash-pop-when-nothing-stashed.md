# P9-001: Fix stash_pop Failure When Nothing Was Stashed

**Phase:** 9 — Bug Fixes (Reported Issues)
**Issue:** [#5](https://github.com/teaguesterling/jetsam/issues/5)
**Priority:** High — causes sync to report failure despite all meaningful steps succeeding
**Affects:** `src/jetsam/core/executor.py`, `src/jetsam/core/planner.py`

## Problem

When `sync` runs with no uncommitted changes, the plan still includes `stash` and
`stash_pop` steps because `state.dirty` can be True due to untracked files. The `stash`
step succeeds (git exits 0, prints "No local changes to save"), but `stash_pop` fails
with "No stash entries found" (git exits 1) because nothing was actually stashed.

Result: sync exits with code 1 despite fetch/merge/push all succeeding.

```
  ✓ stash
  ✓ fetch
  ✓ merge
  ✓ push
  ✗ stash_pop: No stash entries found.
```

## Root Cause

Two contributing factors:

1. **Planner** (`planner.py:100-102`): Adds stash steps whenever `state.dirty is True`.
   But `dirty` includes untracked files, which `git stash push` does not stash by default.

2. **Executor** (`executor.py:243-247`): `_exec_stash_pop` does not check whether a stash
   was actually created before attempting to pop.

## Solution

Fix in the executor — track whether stash actually stored anything, and make stash_pop
a no-op if nothing was stashed. Two approaches (choose one):

### Option A: Check stash count (recommended)

In `_exec_stash`, after running `git stash push`, check if the stash list grew by
comparing `git stash list` output or checking if stdout contains "No local changes to save".
Store a flag in the step result details. In `_exec_stash_pop`, check that flag or check
`git stash list` before popping.

### Option B: Smarter dirty check in planner

Change the planner to only add stash/stash_pop steps when `state.staged` or
`state.unstaged` are non-empty (not just when `dirty` is True from untracked files alone).
This is a narrower fix but doesn't handle the case where stash push legitimately
no-ops for other reasons.

### Suggested implementation (Option A)

```python
# executor.py — _exec_stash
def _exec_stash(step: PlanStep, cwd: str | None) -> StepResult:
    message = step.params.get("message", "")
    args = ["stash", "push"]
    if message:
        args.extend(["-m", message])
    result = run_git_sync(args, cwd=cwd)
    if result.ok:
        actually_stashed = "No local changes to save" not in result.stdout
        return StepResult(step="stash", ok=True, details={"stashed": actually_stashed})
    return StepResult(step="stash", ok=False, error=result.stderr.strip())

# executor.py — _exec_stash_pop: check prior stash result
def _exec_stash_pop(step: PlanStep, cwd: str | None, prior_results: list[StepResult]) -> StepResult:
    # Find matching stash step result
    stash_result = next((r for r in prior_results if r.step == "stash"), None)
    if stash_result and not stash_result.details.get("stashed", True):
        return StepResult(step="stash_pop", ok=True, details={"skipped": True})
    result = run_git_sync(["stash", "pop"], cwd=cwd)
    ...
```

Note: `_exec_stash_pop` currently doesn't receive prior results. The executor dispatch
in `_execute_step` will need to be updated to pass accumulated results, or use a
simpler approach like checking `git stash list` directly.

## Acceptance Criteria

- [ ] `sync` succeeds (exit 0) when there's nothing to stash
- [ ] `sync` still stashes and pops correctly when there are real uncommitted changes
- [ ] `stash_pop` result indicates whether it was skipped
- [ ] Existing tests pass
- [ ] Add test case: sync with untracked-only dirty state

## Estimated Scope

~15-25 lines changed in `executor.py`. Possibly minor changes to `_execute_step` dispatch
or planner dirty check. One new test case.
