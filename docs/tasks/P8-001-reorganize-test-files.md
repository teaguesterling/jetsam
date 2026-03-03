# P8-001: Reorganize Phase Test Files by Feature

**Phase:** 8 — Testing & Polish
**Priority:** Low-medium impact, moderate effort
**Affects:** `tests/test_phase2.py`, `tests/test_phase3.py`, `tests/test_phase4.py`

## Problem

Tests are organized by implementation phase (test_phase2.py, test_phase3.py,
test_phase4.py) rather than by feature. Now that all phases are complete, this
organization makes it harder to find tests for a specific feature:

- Want to find all `ship` tests? They're in test_phase2.py alongside `switch`,
  `checks`, `pr`, and `init` tests.
- Want to find all `start`/`finish` tests? They're in test_phase3.py alongside
  `tidy`, `issues`, `completions`, and `slugify` tests.
- Want to find all `release` tests? They're in test_phase4.py alongside alias
  generation, worktree shared paths, and error recovery tests.

## Solution

Split the phase files into feature-focused test modules:

### From test_phase2.py (35 tests):
- `test_ship.py` — Ship verb tests
- `test_switch.py` — Switch verb tests
- `test_pr.py` — PR verb tests
- `test_checks.py` — Checks verb tests
- `test_init.py` — Init verb tests
- Executor tests → merge into `test_executor.py`

### From test_phase3.py (48 tests):
- `test_start.py` — Start verb tests
- `test_finish.py` — Finish verb tests
- `test_tidy.py` — Tidy verb tests
- `test_issues.py` — Issues verb tests
- `test_prs.py` — PRs list verb tests
- `test_completions.py` — Completions tests
- `test_slugify.py` — Slug generation tests (or merge into test_planner.py)

### From test_phase4.py (35 tests):
- `test_release.py` — Release verb tests
- `test_aliases.py` — Alias system tests
- `test_error_recovery.py` — Error recovery suggestion tests
- Worktree shared paths → merge into `test_worktree.py`

### Keep existing focused test files as-is:
- `test_smoke.py`, `test_state.py`, `test_config.py`, `test_git_wrapper.py`,
  `test_parsers.py`, `test_output.py`, `test_planner.py`, `test_executor.py`,
  `test_cli_verbs.py`, `test_mcp_tools.py`, `test_integration.py`,
  `test_worktree.py`, `test_platform_github.py`, `test_platform_gitlab.py`

## Acceptance Criteria

- [ ] Each test file maps to one feature or module
- [ ] All 269 tests still pass
- [ ] No duplicate test names
- [ ] Remove empty test_phase*.py files
- [ ] Shared fixtures remain in conftest.py (no duplication)
- [ ] Test counts are preserved (no accidentally dropped tests)

## Estimated Scope

Pure file reorganization — no logic changes. ~1-2 hours of careful cut/paste.

## Risks

- Test discovery changes if test names collide across new files
- Shared setup within phase files (class-level) needs to be preserved
- Git blame history is lost for moved tests (acceptable)

## Notes

This is a housekeeping task. It can be deferred indefinitely without impacting
functionality, but it pays dividends every time someone needs to find or modify
tests for a specific feature.
