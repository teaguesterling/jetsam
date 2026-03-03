# P5-005: Trigger Plan Cleanup on Expired Plans

**Phase:** 5 — Quick Wins & Code Quality
**Priority:** Medium impact, low effort
**Affects:** `src/jetsam/core/plans.py`, `src/jetsam/mcp/tools.py`

## Problem

`PlanStore.cleanup_expired()` exists but is never called. Expired plan files accumulate
in `.jetsam/plans/` indefinitely. While each file is small (~1KB), a busy agent
session could create dozens of plans that never get cleaned up.

## Solution

Call `cleanup_expired()` opportunistically in one or both of these locations:

1. **In `_get_store()`** (tools.py) — cleanup runs once when the store is first
   initialized for a session
2. **In `plan_tidy`** — since `tidy` is already about cleanup, it should also
   clean expired plans

Option 1 is the minimal fix. Option 2 adds explicit user-facing cleanup.

```python
# tools.py - _get_store()
def _get_store() -> PlanStore:
    global _plan_store
    if _plan_store is None:
        state = build_state()
        _plan_store = PlanStore(state.repo_root)
        _plan_store.cleanup_expired()  # Clean up on first access
    return _plan_store
```

## Acceptance Criteria

- [ ] Expired plans are cleaned up automatically
- [ ] `tidy` verb cleans expired plans in addition to branches
- [ ] Add test: create expired plan file, verify cleanup removes it
- [ ] No performance impact on normal operations

## Estimated Scope

~5 lines in `tools.py`, ~3 lines in `tidy` planner/executor, 1 new test.
