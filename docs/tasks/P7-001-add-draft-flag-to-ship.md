# P7-001: Add --draft Flag to Ship CLI

**Phase:** 7 — CLI & Features
**Priority:** Medium impact, low effort
**Affects:** `src/jetsam/cli/verbs/ship.py`, `src/jetsam/core/planner.py`

## Problem

The product spec describes draft PR support, and `plan_ship` / `_exec_pr_create`
already handle a `draft` parameter in plan steps. However, the `ship` CLI verb
doesn't expose a `--draft` flag, making it impossible to create draft PRs from
the command line without using `config.pr_draft`.

## Solution

Add `--draft` flag to the ship verb:

```python
@click.command()
@click.option("-m", "--message", help="Commit message and PR title")
@click.option("--draft", is_flag=True, default=False, help="Create PR as draft")
# ... other options
def ship(ctx, message, draft, ...):
    ...
```

Thread `draft` through to `plan_ship()`, which should pass it to the `pr_create`
step params.

### Changes to planner.py

`plan_ship` needs a `draft` parameter:

```python
def plan_ship(
    state, plan_id, message=None, ..., draft: bool = False,
) -> Plan:
    # ...
    if open_pr and not state.pr:
        steps.append(PlanStep(
            action="pr_create",
            params={"title": message or state.branch, "base": target_branch, "draft": draft},
        ))
```

## Acceptance Criteria

- [ ] `jetsam ship --draft -m "wip"` creates a draft PR
- [ ] `draft` parameter flows from CLI → planner → plan step → executor
- [ ] Config `pr_draft` serves as default when `--draft` not specified (depends on P6-001)
- [ ] MCP `ship()` tool already has draft support or gets it added
- [ ] Test for `plan_ship` with `draft=True`

## Estimated Scope

~5 lines in `ship.py`, ~5 lines in `planner.py`, 1-2 new tests.

## Dependencies

- P6-001 (Wire config) — for `pr_draft` config default, but `--draft` flag works standalone
