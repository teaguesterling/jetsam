# P6-003: Include Full Plan Data in to_dict()

**Phase:** 6 — Config & Standardization
**Priority:** Medium impact, low effort
**Affects:** `src/jetsam/core/planner.py`

## Problem

`Plan.to_dict()` omits `params`, `state_hash`, and `scope` from the serialized output:

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "plan_id": self.plan_id,
        "verb": self.verb,
        "steps": [s.to_dict() for s in self.steps],
        "warnings": self.warnings,
    }
```

But `PlanStore.save()` serializes all fields including `state_hash`, `scope`, and `params`.
And `update_plan()` reads/writes `params`. This means:

1. The agent can't see the original parameters of a plan it received
2. The agent can't see which files are in scope
3. There's no way for the agent to know the state_hash for debugging stale plan errors

## Solution

Include all fields in `to_dict()`:

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "plan_id": self.plan_id,
        "verb": self.verb,
        "steps": [s.to_dict() for s in self.steps],
        "warnings": self.warnings,
        "params": self.params,
        "scope": self.scope,
        "state_hash": self.state_hash,
    }
```

## Acceptance Criteria

- [ ] `Plan.to_dict()` includes `params`, `scope`, and `state_hash`
- [ ] MCP tool responses for plan-returning tools include the new fields
- [ ] Existing tests updated for the expanded output shape
- [ ] No breaking changes (new fields are additive)

## Estimated Scope

~3 lines changed in `planner.py`. Update test assertions.
