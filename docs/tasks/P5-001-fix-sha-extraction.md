# P5-001: Fix SHA Extraction in Executor

**Phase:** 5 — Quick Wins & Code Quality
**Priority:** High impact, low effort
**Affects:** `src/jetsam/core/executor.py`

## Problem

The `_exec_commit` function (executor.py:171-184) extracts the commit SHA by scanning
`git commit` output lines, looking for lines starting with `[` and guessing which
space-separated token looks like a hex string. This is fragile across git versions,
locales, and output format changes.

```python
# Current (fragile)
for line in result.stdout.splitlines():
    if line.startswith("["):
        parts = line.split()
        for p in parts:
            if len(p) >= 7 and p.rstrip("]").replace("-", "").isalnum():
                sha = p.rstrip("]")
                break
```

## Solution

After a successful commit, run `git rev-parse --short HEAD` to reliably get the SHA:

```python
if result.ok:
    sha_result = run_git_sync(["rev-parse", "--short", "HEAD"], cwd=cwd)
    sha = sha_result.stdout.strip() if sha_result.ok else ""
    return StepResult(step="commit", ok=True, details={"sha": sha, "message": message})
```

This adds one subprocess call per commit but is completely reliable regardless of
git version or locale.

## Acceptance Criteria

- [ ] `_exec_commit` uses `git rev-parse --short HEAD` for SHA extraction
- [ ] Existing tests still pass
- [ ] No change to `StepResult` shape (sha field still present)

## Estimated Scope

~5 lines changed in `executor.py`. Possibly update test assertions if they validate
specific SHA values.
