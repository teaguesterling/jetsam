# P6-001: Wire Config into Planners

**Phase:** 6 — Config & Standardization
**Priority:** High impact, moderate effort
**Affects:** `src/jetsam/core/planner.py`, `src/jetsam/mcp/tools.py`, CLI verbs

## Problem

`JetsamConfig` defines 9 configuration options (platform, merge_strategy, auto_push,
ship_default, pr_draft, branch_prefix, delete_on_merge, worktree, commit_message),
but `load_config()` is never called by any planner function or MCP tool. All planners
use hardcoded defaults.

This is the single largest gap between the product spec and the implementation.

### Specific gaps:

| Config Option | Expected Behavior | Current Behavior |
|---|---|---|
| `auto_push` | `save` generates push step when true | Always omits push |
| `pr_draft` | `ship`/`pr` creates draft PR when true | Always non-draft |
| `ship_default` | `ship` defaults to PR or merge | Always defaults to PR |
| `merge_strategy` | `finish`/`ship --merge` uses configured strategy | Always "squash" |
| `branch_prefix` | `start` prefixes branch names | Only uses explicit prefix |
| `delete_on_merge` | `finish` respects config | Always deletes |
| `commit_message` | `save`/`ship` uses configured strategy | Always heuristic |

## Solution

### Step 1: Thread config through planners

Each planner function should accept an optional `config: JetsamConfig | None` parameter.
If not provided, call `load_config(state.repo_root)` internally.

```python
def plan_save(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
    config: JetsamConfig | None = None,
) -> Plan:
    if config is None:
        config = load_config(state.repo_root)
    # ... use config.auto_push, config.commit_message, etc.
```

### Step 2: Apply config values as defaults

- `plan_save`: If `config.auto_push`, append push step after commit
- `plan_ship`: Use `config.pr_draft` as default for draft param; use
  `config.ship_default` to decide PR vs merge; use `config.merge_strategy`
- `plan_start`: Use `config.branch_prefix` when no explicit prefix given
- `plan_finish`: Use `config.merge_strategy` as default; use `config.delete_on_merge`
- `plan_sync`: No config changes needed (strategy already parameterized)

### Step 3: Thread config through MCP tools

MCP tools should load config once per request and pass to planners:

```python
@mcp.tool()
def save(message=None, include=None, exclude=None, files=None):
    state = build_state()
    config = load_config(state.repo_root)
    pid = generate_plan_id()
    plan = plan_save(state, plan_id=pid, message=message, ..., config=config)
```

### Step 4: Thread config through CLI verbs

CLI verbs should load config and pass to planners similarly.

## Acceptance Criteria

- [ ] All planner functions accept optional `config` parameter
- [ ] `auto_push` adds push step to `plan_save` output
- [ ] `pr_draft` sets draft=True on PR creation steps
- [ ] `ship_default` controls whether `plan_ship` generates PR or merge steps
- [ ] `merge_strategy` is used as default in `plan_finish` and `plan_ship --merge`
- [ ] `branch_prefix` is used as default in `plan_start`
- [ ] `delete_on_merge` is respected in `plan_finish`
- [ ] CLI verb options override config values (explicit > config > hardcoded default)
- [ ] Tests for each config option's effect on plan generation
- [ ] Existing tests still pass (config defaults match current hardcoded behavior)

## Estimated Scope

~50-80 lines across planner.py, tools.py, and CLI verb files. ~15 new tests.

## Dependencies

None — config module already works. This is purely wiring.
