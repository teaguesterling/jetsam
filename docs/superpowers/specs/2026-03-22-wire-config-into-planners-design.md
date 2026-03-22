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

## Sentinel Detection Strategy

To enforce the precedence rule (explicit param > config > hardcoded default), parameters that overlap with config options must use `None` as their default so the planner can distinguish "caller set this" from "caller used the default."

**Planner signature changes:**
- `plan_ship`: `open_pr: bool = True` → `open_pr: bool | None = None`, `merge: bool = False` → `merge: bool | None = None`. Add `draft: bool | None = None`.
- `plan_start`: `worktree: bool = False` → `worktree: bool | None = None`
- `plan_finish`: `strategy: str = "squash"` → `strategy: str | None = None`, `no_delete: bool = False` → `no_delete: bool | None = None`

**CLI click option changes:**
- `finish --strategy`: `default="squash"` → `default=None`
- `start --prefix`: keep `default=""` (empty string is the "not set" sentinel for prefix)

**MCP tool parameter changes:** Same pattern — use `None` defaults where config should fill in.

When a parameter is `None`, the planner uses the config value. When explicitly set, the explicit value wins.

## Planner Changes

Each affected planner gets `config: JetsamConfig | None = None`. If not provided, calls `load_config(state.repo_root)`.

| Planner | Config Options | Behavior |
|---|---|---|
| `plan_save` | `auto_push` | Append `push` step after commit when true and not on default branch (see rationale below) |
| `plan_ship` | `pr_draft`, `ship_default`, `merge_strategy` | `pr_draft` sets default for new `draft` param on PR creation step; `ship_default` decides PR vs merge when `open_pr` and `merge` are both `None`; `merge_strategy` passed to `pr_merge` step params |
| `plan_start` | `branch_prefix`, `worktree` | Config prefix when no explicit prefix given; config worktree resolved to bool (see below) |
| `plan_finish` | `merge_strategy`, `delete_on_merge` | Config strategy when `strategy` is `None`; config `delete_on_merge` when `no_delete` is `None` (mapping: `no_delete = not config.delete_on_merge`) |

### plan_save auto_push — default branch guard

When `auto_push=True`, a `push` step is appended after commit **only when not on the default branch**. Rationale: pushing directly to main/master should be an explicit action via `sync`, not an automatic side effect of `save`. This is a safety guard — the config enables auto-push for feature branch workflows, not for direct-to-main commits.

### plan_ship — new `draft` parameter

`plan_ship` currently has no `draft` parameter. This task adds `draft: bool | None = None`. When `None`, uses `config.pr_draft`. The value flows to the `pr_create` step's params as `"draft": True/False`.

### plan_ship — merge_strategy in pr_merge step

Currently `plan_ship`'s `pr_merge` step does not include a `strategy` param (unlike `plan_finish` which does). This task adds `"strategy": strategy` to `plan_ship`'s `pr_merge` step params, resolved from explicit param > config > `"squash"`.

### plan_finish — no_delete / delete_on_merge mapping

The planner param `no_delete: bool` is a double negative of config `delete_on_merge: bool`. When `no_delete` is `None` (not explicitly set by caller), the planner resolves it as: `no_delete = not config.delete_on_merge`. When explicitly set, the explicit value wins.

### plan_start worktree resolution

The config `worktree` field is `"auto" | "always" | "never"` but the planner param is `worktree: bool | None`. Resolution when `worktree` is `None` (not explicitly set):
- `"auto"` → `False` (current behavior)
- `"always"` → `True`
- `"never"` → `False`

When caller explicitly passes `worktree=True` or `worktree=False`, the explicit value wins (including overriding `"never"` or `"always"`). Precedence rule has no exceptions.

## Entry Point Changes

### MCP Tools (`tools.py`)

Each tool function adds config loading after `build_state()` and passes it to the planner. Parameters that overlap with config use `None` defaults so the planner can detect explicit vs default.

Only tools calling affected planners need changes: `save`, `ship`, `start`, `finish`.

### CLI Verbs

Same pattern. Click options that overlap with config change to `default=None` (except `--prefix` which uses `""` as sentinel). The verb passes the CLI arg value through to the planner — `None` means "use config default."

Only affected verbs need changes: `save`, `ship`, `start`, `finish`.

### No changes to `build_state()` or `execute_plan()`

Config flows through the planner layer only.

## Testing Strategy

~17 new tests in `test_planner.py`. Tests create a `JetsamConfig(...)` directly (no file I/O) and pass it to planner functions.

**Tests per config option:**

- `auto_push=True` → `plan_save` includes `push` step
- `auto_push=True` on default branch → no push step (safety guard)
- `auto_push=False` → no push step (regression)
- `pr_draft=True` → `plan_ship` PR step has `draft=True`
- `ship_default="merge"` → `plan_ship` generates merge steps (no explicit open_pr/merge)
- `ship_default="pr"` → generates PR steps (regression)
- `merge_strategy="rebase"` → `plan_finish` merge step uses rebase
- `merge_strategy="rebase"` → `plan_ship` merge step uses rebase
- `merge_strategy="merge"` → uses merge
- `branch_prefix="feature/"` → `plan_start` prefixes branch
- `branch_prefix=""` → no prefix (regression)
- `delete_on_merge=False` → `plan_finish` skips branch_delete
- `delete_on_merge=True` → includes branch_delete (regression)
- `worktree="always"` → `plan_start` uses worktree_add
- `worktree="never"` → `plan_start` uses checkout
- Explicit `worktree=True` overrides config `"never"`
- Explicit param overrides config value (e.g., `strategy="merge"` overrides `config.merge_strategy="squash"`)
- Config=None → planner loads config internally

**Existing tests pass unchanged** because config defaults match current hardcoded behavior.

## Files Modified

| File | Change |
|---|---|
| `src/jetsam/core/planner.py` | Add `config` param to 4 planners, add `draft` param to `plan_ship`, apply config defaults, change overlapping param defaults to `None` |
| `src/jetsam/mcp/tools.py` | Load config in 4 tool functions, pass to planners, change overlapping param defaults to `None` |
| `src/jetsam/cli/verbs/save.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/ship.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/start.py` | Load config, pass to planner |
| `src/jetsam/cli/verbs/finish.py` | Load config, pass to planner, change `--strategy` default to `None` |
| `tests/test_planner.py` | ~17 new tests |

## Out of Scope

- `commit_message` config option (deferred — needs new behavior, not just wiring)
- `platform` config option (used elsewhere, not in planners)
- `worktree` config option in `plan_sync` (already parameterized)
- Changes to `build_state()` or `execute_plan()`
