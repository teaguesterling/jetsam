# Ship/Save File Scoping and Empty Commit Fixes — Design Spec

**Date:** 2026-03-22
**Scope:** Fix `_resolve_files()` scoping (#4) and skip empty commits in `plan_ship()` (#7)

## Problem

Two related bugs in the planner layer:

1. **#4 — `files` parameter doesn't scope staging exclusively.** `plan_ship()`
   does not accept a `files` parameter, so `ship(files=[...])` cannot scope
   staging. Additionally, `_resolve_files()` already returns `files` early when
   provided, but does not apply `exclude` filtering to that path.

2. **#7 — `ship` fails when nothing to commit but push/PR needed.** When changes
   have already been committed (via `save`) but not pushed, `ship`
   unconditionally adds a commit step that fails with "nothing to commit",
   aborting before reaching the push/PR steps. The commit-needed check uses
   `state.dirty` which is true even for untracked-only changes.

## Fixes

### Fix 1: `_resolve_files()` — add `exclude` filtering to explicit `files` path

`_resolve_files()` already has an early return when `files` is provided (line
590: `if files: return files`). This correctly scopes to exactly the listed
files. However, it does not apply `exclude` filtering.

**Change:** When `files` is provided and `exclude` is also provided, filter
the files list through the exclude pattern before returning.

```python
if files:
    if exclude:
        return [f for f in files if not _matches_glob(f, exclude)]
    return files
```

No other changes to `_resolve_files()`. The existing include/exclude behavior
for the non-`files` path is unchanged.

### Fix 2: `plan_ship()` — accept `files` parameter

`plan_ship()` lacks a `files` parameter. The MCP tool `ship()` in `tools.py`
also lacks it.

**Changes:**
- Add `files: list[str] | None = None` to `plan_ship()` signature
- Pass `files` through to `_resolve_files(state, include, exclude, files)`
- Add `files` to the MCP tool `ship()` signature and pass to `plan_ship()`
- Add `"files": files` to the plan params dict

### Fix 3: `plan_ship()` — skip commit when nothing to commit

The current code at line 211 checks `if all_staged or state.dirty:` to decide
whether to add a commit step. `state.dirty` includes untracked-only changes,
which shouldn't trigger a commit (untracked files aren't staged by default).

**Change:** Replace `state.dirty` with a check for actual committable changes:

```python
has_something_to_commit = bool(target_files or state.staged)
```

If `has_something_to_commit` is false:
- Skip the stage and commit steps entirely
- If `state.ahead > 0`: generate push (+PR) steps only
- If `state.ahead == 0` and `open_pr` is true and no PR exists: generate
  PR-create step only (valid workflow: code pushed via `sync`, user now wants
  a PR)
- If `state.ahead == 0` and no PR needed: warn "nothing to commit or push",
  return plan with no steps

This also fixes the `state.dirty` over-triggering — untracked files alone no
longer cause a commit step to be generated.

### Fix 4: `plan_save()` — skip commit step when nothing to save

`plan_save()` already appends a warning when nothing to save (lines 62-63) but
unconditionally generates a commit step anyway (lines 74-80).

**Change:** When `target_files` is empty and `state.staged` is empty, return
the plan early with just the warning and no steps. Do not append the commit step.

## Files changed

### Modified files
- `src/jetsam/core/planner.py` — `_resolve_files()`, `plan_save()`, `plan_ship()`
- `src/jetsam/mcp/tools.py` — add `files` parameter to `ship()` tool

### Test cases
- `_resolve_files` with explicit `files` returns only those files (existing behavior, verify)
- `_resolve_files` with `files` + `exclude` filters correctly (new)
- `_resolve_files` with `files=None` preserves existing behavior (existing, verify)
- `plan_ship` with `files` scopes stage step to listed files only
- `plan_ship` with nothing to commit but `ahead > 0` generates push-only plan
- `plan_ship` with nothing to commit, `ahead == 0`, `open_pr=True` generates PR-only plan
- `plan_ship` with nothing to commit, `ahead == 0`, no PR returns warning
- `plan_ship` with `files` listing clean files + `ahead > 0` generates push-only plan
- `plan_save` with nothing to save returns warning and empty steps
- `plan_save` with nothing to save does not include commit step
- MCP `ship()` tool accepts and passes `files` parameter

## Limitations

- No validation that files in the `files` list exist or are known to git. If a
  nonexistent path is passed, the stage step will fail at execution time. This
  matches `git add` behavior and is acceptable.

## Config note (future)

`pr_default: true|false` in `.jetsam/config.yaml` to control whether `ship`
creates a PR by default. Not implemented in this spec — noted for future work.
