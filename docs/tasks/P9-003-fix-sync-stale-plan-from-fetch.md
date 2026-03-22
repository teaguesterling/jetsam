# P9-003: Fix Stale Plan Error When Fetch Changes Repo State

**Phase:** 9 — Bug Fixes (Reported Issues)
**Issue:** [#2](https://github.com/teaguesterling/jetsam/issues/2)
**Related:** [#3](https://github.com/teaguesterling/jetsam/issues/3) (simpler sync on default branch)
**Priority:** High — sync is unusable when remote has new commits
**Affects:** `src/jetsam/core/executor.py`, `src/jetsam/core/state.py`, `src/jetsam/core/planner.py`

## Problem

`sync` creates a plan with a state hash computed at plan-creation time. The plan
includes a `fetch` step. When `confirm()` runs, the executor validates the state hash
*before* executing any steps. But the fetch step — which is part of the plan itself —
changes local refs, which changes `ahead`/`behind` counts, which changes the state hash.

This creates an unwinnable race condition:
1. `sync()` → computes hash H1, returns plan
2. `confirm(plan_id)` → rebuilds state, computes hash H2
3. If remote has new commits since plan creation, H1 ≠ H2 → `stale_plan` error
4. Retrying `sync()` + `confirm()` hits the same issue if anything changed

The state hash for sync (unscoped) includes: `branch`, `head_sha`, `dirty`, `staged`,
`unstaged`, `untracked`, `ahead`, `behind`. The `ahead`/`behind` counts change when
fetch updates remote tracking refs.

## Solution Options

### Option A: Exclude ahead/behind from sync hash (simplest)

The staleness check for sync should detect local changes (someone modified files or
switched branches), not remote changes (new commits fetched). Remove `ahead` and `behind`
from the unscoped hash, or introduce a sync-specific scope.

**Pro:** Minimal change, doesn't alter the plan/confirm pattern.
**Con:** Reduces sensitivity — won't detect if someone else pushed to the same branch.

### Option B: Validate hash before fetch, not before all steps

Split execution into phases: validate hash → run fetch → re-hash → run remaining steps.
The pre-fetch hash validates that local state hasn't changed. Post-fetch, the plan
adapts to the new reality.

**Pro:** Precise validation at the right point in time.
**Con:** More complex executor changes, introduces multi-phase execution.

### Option C: Auto-execute sync plans (from issue #2 suggestion)

Add an `auto_confirm` flag to plans. Low-risk operations like sync execute immediately
without the plan/confirm round-trip. The plan is still generated (for display/logging)
but doesn't require explicit confirmation.

**Pro:** Eliminates the timing window entirely. Better UX for routine operations.
**Con:** Changes the plan/confirm contract. Need clear criteria for what qualifies
as auto-confirmable.

### Recommended: Option A + partial Option C

1. Remove `ahead`/`behind` from the sync state hash (fixes the immediate bug)
2. Consider adding `auto_confirm` as a follow-up (better UX, separate task)

### Implementation sketch (Option A)

In `planner.py:plan_sync()`, set a scope that excludes ahead/behind:

```python
# Instead of using the full unscoped hash, use a sync-appropriate scope
# that ignores ahead/behind (which change on fetch)
sync_hash_data = {
    "branch": state.branch,
    "head_sha": state.head_sha,
    "dirty": state.dirty,
    "staged": sorted(state.staged),
    "unstaged": sorted(state.unstaged),
    "untracked": sorted(state.untracked),
}
state_hash = hashlib.sha256(json.dumps(sync_hash_data, sort_keys=True).encode()).hexdigest()[:16]
```

Or add a `compute_hash` mode/parameter that excludes remote tracking info.

## Acceptance Criteria

- [ ] `sync` + `confirm` succeeds even when remote has new commits
- [ ] `sync` still detects genuinely stale state (local file changes, branch switches)
- [ ] Hash change doesn't break `save`/`ship` staleness checks
- [ ] Existing tests pass
- [ ] Add test case: sync plan remains valid after simulated fetch

## Estimated Scope

~10-20 lines changed in `state.py` or `planner.py`. Test updates for hash behavior.
