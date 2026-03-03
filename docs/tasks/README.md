# Task Plans

Post-v0.1 improvement tasks identified from a systematic code review.
Phases continue from the original implementation phases (1-4).

## Phase 5 — Quick Wins & Code Quality

High-impact, low-effort fixes. No architectural changes.

| Task | Description | Effort |
|------|-------------|--------|
| [P5-001](P5-001-fix-sha-extraction.md) | Fix fragile SHA extraction in executor | ~5 lines |
| [P5-002](P5-002-consolidate-platform-error.md) | Consolidate PlatformError into base module | ~10 lines |
| [P5-003](P5-003-add-py-typed-marker.md) | Add py.typed marker for PEP 561 | 1 file |
| [P5-004](P5-004-add-test-coverage.md) | Add test coverage measurement | Config only |
| [P5-005](P5-005-trigger-plan-cleanup.md) | Trigger cleanup of expired plans | ~10 lines |

## Phase 6 — Config & Standardization

Wire config into planners, standardize error handling, improve data completeness.

| Task | Description | Effort |
|------|-------------|--------|
| [P6-001](P6-001-wire-config-into-planners.md) | Wire JetsamConfig into all planners | ~80 lines + tests |
| [P6-002](P6-002-standardize-mcp-error-returns.md) | Standardize MCP tool error returns | ~40 lines + tests |
| [P6-003](P6-003-plan-to-dict-completeness.md) | Include full plan data in to_dict() | ~3 lines |
| [P6-004](P6-004-thread-state-through-executor.md) | Thread RepoState through executor | ~40 lines |

## Phase 7 — CLI & Features

New CLI capabilities from the product spec.

| Task | Description | Effort |
|------|-------------|--------|
| [P7-001](P7-001-add-draft-flag-to-ship.md) | Add --draft flag to ship verb | ~10 lines |
| [P7-002](P7-002-cli-edit-flow.md) | Implement interactive edit flow for plans | ~150 lines |
| [P7-003](P7-003-add-config-verb.md) | Add config view/set verb | ~100 lines |

## Phase 8 — Testing & Polish

Test improvements and developer experience.

| Task | Description | Effort |
|------|-------------|--------|
| [P8-001](P8-001-reorganize-test-files.md) | Reorganize phase test files by feature | File moves |
| [P8-002](P8-002-negative-path-platform-tests.md) | Add negative path tests for platforms | ~200 lines |
| [P8-003](P8-003-add-structured-logging.md) | Add structured logging to stderr | ~80 lines |

## Dependency Graph

```
P5-* ──── no dependencies (can be done in any order)

P6-001 ←── P7-001 (draft flag uses config defaults)
P6-001 ←── P7-003 (config verb more useful when config is wired in)
P5-002 ←── P8-002 (platform tests should import consolidated error)

P6-002 ──── no dependencies
P6-003 ──── no dependencies
P6-004 ──── no dependencies
P7-002 ──── no dependencies
P8-001 ──── no dependencies
P8-003 ──── no dependencies
```
