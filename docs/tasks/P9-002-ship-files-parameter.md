# P9-002: Add `files` Parameter to `ship` Verb

**Phase:** 9 — Bug Fixes (Reported Issues)
**Issue:** [#4](https://github.com/teaguesterling/jetsam/issues/4)
**Priority:** High — user-facing bug where explicit file lists are silently ignored
**Affects:** `src/jetsam/mcp/tools.py`, `src/jetsam/core/planner.py`

## Problem

When calling `ship(files=["specific-file.md"])`, the `files` parameter is silently
ignored because the `ship` MCP tool and `plan_ship` planner don't accept a `files`
parameter. The `save` verb supports `files` correctly, but `ship` does not — an
asymmetry in the API.

Because `files` is ignored, `ship` falls back to default staging behavior: stage all
modified tracked files. This causes unrelated files to be included in the commit.

## Root Cause

1. **MCP tool** (`tools.py:96-122`): `ship()` function signature lacks `files` parameter.
   It passes `include` and `exclude` to `plan_ship` but not `files`.

2. **Planner** (`planner.py:158-258`): `plan_ship()` signature lacks `files` parameter.
   It calls `_resolve_files(state, include, exclude)` without passing `files`.

The `save` verb handles this correctly:
- `save()` MCP tool accepts `files` parameter
- `plan_save()` accepts `files` and passes it to `_resolve_files()`
- `_resolve_files()` already has `files` support: `if files: return files`

## Solution

Thread the `files` parameter through `ship` the same way `save` does.

### Changes needed

**1. `src/jetsam/mcp/tools.py` — add `files` to `ship()` signature:**

```python
def ship(
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,   # Add this
    to: str | None = None,
    pr: bool = True,
    merge: bool = False,
) -> dict[str, Any]:
    ...
    plan = plan_ship(
        state, plan_id=pid,
        message=message, include=include, exclude=exclude,
        files=files,   # Pass through
        to=to, open_pr=pr, merge=merge,
    )
```

**2. `src/jetsam/core/planner.py` — add `files` to `plan_ship()` signature:**

```python
def plan_ship(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,   # Add this
    to: str | None = None,
    open_pr: bool = True,
    merge: bool = False,
) -> Plan:
    ...
    target_files = _resolve_files(state, include, exclude, files=files)  # Pass through
```

No changes needed to `_resolve_files` or `_exec_stage` — they already handle explicit
file lists correctly.

## Acceptance Criteria

- [ ] `ship(files=["a.txt"])` stages only `a.txt`, not other modified files
- [ ] `ship()` without `files` retains current default behavior (stage modified tracked files)
- [ ] `ship(files=..., include=...)` — `files` takes precedence (matches `save` behavior)
- [ ] Existing tests pass
- [ ] Add test case: `plan_ship` with explicit files produces correct stage step

## Estimated Scope

~5 lines changed across 2 files. One new test case.
