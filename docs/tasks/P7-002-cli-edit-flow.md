# P7-002: Implement CLI Edit Flow for Plans

**Phase:** 7 — CLI & Features
**Priority:** Medium impact, moderate effort
**Affects:** `src/jetsam/cli/verbs/` (save, ship, sync, start, finish, release, tidy)

## Problem

The product spec describes a three-option interactive flow:

```
[e]dit / [c]onfirm / [a]bort: e
exclude> test_parser.cpp
```

The current implementation only offers `[c]onfirm / [a]bort`. Users can't modify a
plan interactively before confirming it from the CLI.

## Solution

### Step 1: Add edit option to confirmation prompt

```python
# Current
choice = click.prompt("[c]onfirm / [a]bort", type=click.Choice(["c", "a"]))

# Proposed
choice = click.prompt("[e]dit / [c]onfirm / [a]bort", type=click.Choice(["e", "c", "a"]))
```

### Step 2: Implement edit loop

When `e` is selected, prompt for modifications based on the verb:

**For save/ship (file-based verbs):**
- `exclude> <pattern>` — remove files matching glob from stage step
- `message> <text>` — change commit message
- Show updated plan after each edit
- Return to `[e]dit / [c]onfirm / [a]bort` prompt

**For sync:**
- `strategy> <rebase|merge>` — change integration strategy
- Show updated plan

**For other verbs:**
- `message> <text>` — change commit message (where applicable)

### Step 3: Use update_plan() from plans.py

The edit loop should use `update_plan()` to modify the plan, which already handles
message changes and file exclusion.

### Step 4: Extract shared prompt logic

Since 7+ verbs use the same confirm pattern, extract a shared function:

```python
def confirm_or_edit_plan(plan: Plan, json_mode: bool, dry_run: bool) -> Plan | None:
    """Show plan, prompt for confirm/edit/abort. Returns final plan or None."""
    ...
```

## Acceptance Criteria

- [ ] `[e]dit` option available in all plan-based verbs
- [ ] Edit loop supports `exclude>` and `message>` modifications
- [ ] Updated plan is displayed after each edit
- [ ] Edit loop can be repeated (multiple edits before confirm)
- [ ] `--execute` and `--json` modes skip the edit flow (same as current)
- [ ] Shared confirm/edit function reduces duplication across verbs
- [ ] Tests for edit flow (at minimum: exclude a file, change message)

## Estimated Scope

~100-150 lines: shared confirm function (~60 lines), updates to each verb (~5 lines each),
tests (~40 lines).

## Dependencies

None — `update_plan()` already exists in `plans.py`.
