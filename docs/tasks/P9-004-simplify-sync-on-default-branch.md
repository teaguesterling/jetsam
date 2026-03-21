# P9-004: Simplify Sync on Default Branch

**Phase:** 9 — Bug Fixes (Reported Issues)
**Issue:** [#3](https://github.com/teaguesterling/jetsam/issues/3)
**Related:** [#2](https://github.com/teaguesterling/jetsam/issues/2) (stale plan from fetch)
**Depends on:** P9-001 (stash_pop fix), P9-003 (stale plan fix)
**Priority:** Medium — UX improvement, has workarounds
**Affects:** `src/jetsam/core/planner.py`

## Problem

On the default branch after a local commit, the common workflow is just "push my commit."
But `sync` generates a heavy plan: `stash → fetch → merge → push → stash_pop`. This
adds complexity and creates more surface area for the stale_plan and stash_pop bugs
(#2, #5).

The stash steps are especially problematic: if dirty state is only from untracked files,
stashing is a no-op that can cause stash_pop to fail (see P9-001).

## Current Behavior

`plan_sync` in `planner.py:91-155`:
- Always adds stash/stash_pop if `state.dirty`
- Always fetches
- Adds merge step if behind remote
- Adds push if `state.ahead > 0`

On default branch with local commits and no remote changes, this produces:
```
stash → fetch → merge → push → stash_pop
```
When a simple `push` would suffice.

## Solution

Add intelligence to `plan_sync` for the default-branch-ahead-only case:

### Simplified plan when all conditions are met:

1. On default branch (`state.branch == state.default_branch`)
2. Ahead of remote (`state.ahead > 0`)
3. Not behind remote (`state.behind == 0`)
4. No staged or unstaged changes (`not state.staged and not state.unstaged`)
   - Untracked files alone don't require stashing

When all conditions hold, generate a minimal plan: `fetch → push` (or just `push`).

### Implementation sketch

```python
def plan_sync(state: RepoState, plan_id: str, strategy: str | None = None) -> Plan:
    steps: list[PlanStep] = []
    is_default = state.branch == state.default_branch

    # Determine if stash is actually needed (not just untracked files)
    needs_stash = bool(state.staged or state.unstaged)

    if needs_stash:
        steps.append(PlanStep(action="stash", params={"message": "jetsam sync auto-stash"}))

    # Fast path: default branch, ahead only, clean working tree
    if is_default and state.ahead > 0 and state.behind == 0 and not needs_stash:
        steps.append(PlanStep(action="push", params={...}))
        return Plan(verb="sync", steps=steps, ...)

    # Normal path: fetch + merge/rebase + push
    steps.append(PlanStep(action="fetch", params={"remote": "origin"}))
    ...
```

### Considerations

- The fast path skips fetch, so it won't detect if remote has diverged. This is
  acceptable because `git push` will reject non-fast-forward pushes anyway.
- Users who want the full fetch+merge can use `sync --strategy=merge` or similar.
- The stash threshold change (staged/unstaged only, not untracked) is also applied
  in the normal path — this overlaps with P9-001 but addresses it at the planner level.

## Acceptance Criteria

- [ ] On default branch with only local commits ahead: plan is `push` (or `fetch → push`)
- [ ] On default branch with both ahead and behind: full stash/fetch/merge/push plan
- [ ] On feature branch: behavior unchanged
- [ ] Dirty working tree (staged/unstaged changes): stash steps still included
- [ ] Untracked-only dirty state: stash steps skipped
- [ ] Existing tests pass
- [ ] Add test cases for the simplified default-branch path

## Estimated Scope

~20-30 lines changed in `planner.py`. 2-3 new test cases.
