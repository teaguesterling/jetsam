# P5-004: Add Test Coverage Measurement

**Phase:** 5 — Quick Wins & Code Quality
**Priority:** High impact, low effort
**Affects:** `pyproject.toml`, CI configuration

## Problem

There are 269 tests but no coverage measurement. Without quantitative coverage data,
it's impossible to know which code paths are untested. The project uses `pytest` but
doesn't include `pytest-cov`.

## Solution

1. Add `pytest-cov` to dev dependencies in `pyproject.toml`
2. Configure coverage in `pyproject.toml`
3. Update CI to report coverage

```toml
# pyproject.toml additions

[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-cov>=4.0",
]

[tool.coverage.run]
source = ["jetsam"]
branch = true

[tool.coverage.report]
show_missing = true
skip_empty = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
]
```

3. Update the test command in `.lq/commands.toml` to include coverage
4. Consider adding a coverage threshold once baseline is established

## Acceptance Criteria

- [ ] `pytest-cov` in dev dependencies
- [ ] `[tool.coverage.*]` configured in `pyproject.toml`
- [ ] `pytest --cov=jetsam --cov-report=term-missing` runs successfully
- [ ] Coverage baseline documented (expected ~80%+ given current test suite)
- [ ] CI reports coverage (optional: enforce minimum threshold)

## Estimated Scope

Config changes in `pyproject.toml` and `.lq/commands.toml`. No source code changes.
