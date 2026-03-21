# P9-004: Simplify Sync on Default Branch — Design Spec

**Date:** 2026-03-21
**Task:** [P9-004](../../tasks/P9-004-simplify-sync-on-default-branch.md)
**Issue:** [#3](https://github.com/teaguesterling/jetsam/issues/3)
**Affects:** `src/jetsam/core/planner.py`, `tests/test_planner.py`

## Problem

On the default branch with only local commits ahead, `sync` generates a heavy plan:
`stash → fetch → merge → push → stash_pop`. A simple `push` would suffice.

Additionally, `state.dirty` includes untracked files, which `git stash push` doesn't
stash by default. This causes unnecessary stash/stash_pop steps and contributes to
the stash_pop failure described in P9-001.

## Design

### Approach: Fast path + smarter stash threshold

Two changes to `plan_sync` in `planner.py`:

#### 1. Replace `state.dirty` with `needs_stash`

```python
needs_stash = bool(state.staged or state.unstaged)
```

Use `needs_stash` instead of `state.dirty` for all stash/stash_pop decisions in
`plan_sync`. This affects two locations:
- **Line 100-102**: stash step + warning (currently guarded by `state.dirty`)
- **Line 145-146**: stash_pop step (currently guarded by `state.dirty`)

Both change to use `needs_stash`. Untracked files alone no longer trigger stashing.

#### 2. Fast path early return

When all of these conditions hold:
- On default branch (`state.branch == state.default_branch`)
- Ahead of remote (`state.ahead > 0`)
- Not behind remote (`state.behind == 0`)
- No stash needed (`not needs_stash`)
- No explicit strategy requested (`strategy is None`)

Generate a minimal plan containing only a `push` step and return immediately.
No fetch, no merge, no stash.

**Why skip fetch?** `git push` already rejects non-fast-forward pushes, so the
push itself serves as a safety check. Users who want fetch+merge can pass an
explicit strategy, which bypasses the fast path.

### Code sketch

```python
def plan_sync(state, plan_id, strategy=None):
    steps = []
    warnings = []

    needs_stash = bool(state.staged or state.unstaged)

    if needs_stash:
        warnings.append("Working tree is dirty — changes will be stashed during sync")
        steps.append(PlanStep(action="stash", params={"message": "jetsam sync auto-stash"}))

    # Fast path: default branch, ahead only, clean working tree, no explicit strategy
    is_default = state.branch == state.default_branch
    if is_default and state.ahead > 0 and state.behind == 0 and not needs_stash and strategy is None:
        steps.append(PlanStep(action="push", params={
            "branch": state.branch, "remote": "origin", "set_upstream": state.upstream is None,
        }))
        return Plan(plan_id=plan_id, verb="sync", steps=steps,
                    state_hash=state.compute_hash(), warnings=warnings,
                    params={"strategy": strategy})

    # Normal path continues: fetch, merge/rebase, push
    # (unchanged from current implementation except stash_pop guard)
    ...

    if needs_stash:  # was: if state.dirty
        steps.append(PlanStep(action="stash_pop"))
```

## What doesn't change

- Feature branch behavior (rebase by default, push always)
- Default branch with `behind > 0` (full fetch/merge plan)
- Explicit `strategy` parameter handling
- `plan_switch` and `plan_start` stash logic (those still use `state.dirty`)

## Relationship to P9-001

This design implements P9-001's "Option B" (planner-level fix) for `plan_sync`.
P9-001's "Option A" (executor-level resilience) remains valuable as a separate,
complementary fix for cases where stash is planned but `git stash push` no-ops
for reasons the planner can't predict.

## Test plan

New test cases for `TestPlanSync`:

1. **`test_default_branch_ahead_only_fast_path`** — default branch, ahead=1, behind=0,
   clean tree → plan is `[push]` only
2. **`test_default_branch_untracked_only_fast_path`** — default branch, ahead=1, behind=0,
   dirty=True but staged=[] and unstaged=[] (untracked only) → plan is `[push]` only,
   no stash steps
3. **`test_default_branch_ahead_and_behind_full_plan`** — default branch, ahead=1, behind=2 →
   full plan with fetch/merge, no fast path
4. **`test_default_branch_ahead_with_staged_changes`** — default branch, ahead=1,
   staged changes → full plan with stash/fetch/merge/push/stash_pop
5. **`test_default_branch_explicit_strategy_skips_fast_path`** — default branch, ahead=1,
   behind=0, clean tree, `strategy="merge"` → full plan with fetch/merge (fast path bypassed)

Existing tests must continue to pass unchanged.

**Note:** The existing `test_default_branch_merge` test uses `upstream="origin/feature"`
with `branch="main"`, which is an incoherent state. It still passes because the merge
step fires unconditionally on the normal path. Cleaning up test fixtures is out of scope
for this change.

## Scope

~15-20 lines changed in `planner.py`. 5 new test cases in `test_planner.py`.
