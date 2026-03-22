# Wire Config into Planners — Design Spec

**Task:** P6-001
**Date:** 2026-03-22
**Status:** Approved

## Problem

`JetsamConfig` defines configuration options but `load_config()` is never called by any planner function or MCP tool. All planners use hardcoded defaults.

## Approach

**Approach B — Config loaded at entry points, passed to planners.** CLI verbs and MCP tools load config once per request and pass it to planners. Planners accept an optional `config` parameter and fall back to `load_config(state.repo_root)` if not provided.

**Precedence:** explicit param > config value > hardcoded default.

## Scope

Six config options are wired through. `commit_message` is excluded — its alternative strategies (`prompt`, `llm`) require new behavior beyond wiring, so it's deferred to a separate task.

`plan_sync`, `plan_tidy`, `plan_release`, `plan_switch` receive no config wiring.

## Planner Changes

Each affected planner gets `config: JetsamConfig | None = None`. If not provided, calls `load_config(state.repo_root)`.

| Planner | Config Options | Behavior |
|---|---|---|
| `plan_save` | `auto_push` | Append `push` step after commit when true and not on default branch |
| `plan_ship` | `pr_draft`, `ship_default`, `merge_strategy` | `pr_draft` sets default draft param on PR creation; `ship_default` decides PR vs merge when neither `open_pr` nor `merge` is explicitly set; `merge_strategy` used in merge step params |
| `plan_start` | `branch_prefix`, `worktree` | Config prefix when no explicit prefix given; config worktree (`auto`/`always`/`never`) resolved to bool when caller uses default |
| `plan_finish` | `merge_strategy`, `delete_on_merge` | Config strategy replaces hardcoded `"squash"` default; `delete_on_merge=False` skips branch_delete step |

### plan_start worktree resolution

The config `worktree` field is `"auto" | "always" | "never"` but the planner param is `worktree: bool`. Resolution when caller passes the default (`False`):
- `"auto"` → `False` (current behavior)
- `"always"` → `True`
- `"never"` → `False`

When caller explicitly passes `worktree=True`, config `"never"` overrides to `False`.

## Entry Point Changes

### MCP Tools (`tools.py`)

Each tool function adds two lines after `build_state()`:

```python
config = load_config(state.repo_root)
plan = plan_xxx(..., config=config)
```

Only tools calling affected planners need changes: `save`, `ship`, `start`, `finish`.

### CLI Verbs

Same pattern. CLI args that overlap with config (e.g., `--strategy`, `--no-delete`, `--prefix`) take precedence — the verb passes the CLI arg if provided, otherwise lets the planner use config defaults.

Only affected verbs need changes: `save`, `ship`, `start`, `finish`.

### No changes to `build_state()` or `execute_plan()`

Config flows through the planner layer only.

## Testing Strategy

~15 new tests in `test_planner.py`. Tests create a `JetsamConfig(...)` directly (no file I/O) and pass it to planner functions.

**Tests per config option:**

- `auto_push=True` → `plan_save` includes `push` step
- `auto_push=False` → no push step (regression)
- `pr_draft=True` → `plan_ship` PR step has `draft=True`
- `ship_default="merge"` → `plan_ship` generates merge steps (no explicit open_pr/merge)
- `ship_default="pr"` → generates PR steps (regression)
- `merge_strategy="rebase"` → `plan_finish` merge step uses rebase
- `merge_strategy="merge"` → uses merge
- `branch_prefix="feature/"` → `plan_start` prefixes branch
- `branch_prefix=""` → no prefix (regression)
- `delete_on_merge=False` → `plan_finish` skips branch_delete
- `delete_on_merge=True` → includes branch_delete (regression)
- `worktree="always"` → `plan_start` uses worktree_add
- `worktree="never"` → `plan_start` uses checkout even when worktree requested
- Explicit param overrides config value
- Config=None → planner loads config internally

**Existing tests pass unchanged** because config defaults match current hardcoded behavior.

## Files Modified

| File | Change |
|---|---|
| `src/jetsam/core/planner.py` | Add `config` param to 4 planners, apply config defaults |
| `src/jetsam/mcp/tools.py` | Load config in 4 tool functions, pass to planners |
| `src/jetsam/cli/verbs/save.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/ship.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/start.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/finish.py` | Load config, pass to planner |
| `tests/test_planner.py` | ~15 new tests |

## Out of Scope

- `commit_message` config option (deferred — needs new behavior, not just wiring)
- `platform` config option (used elsewhere, not in planners)
- `worktree` config option in `plan_sync` (already parameterized)
- Changes to `build_state()` or `execute_plan()`
