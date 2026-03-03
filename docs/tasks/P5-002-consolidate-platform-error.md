# P5-002: Consolidate PlatformError into Base Module

**Phase:** 5 — Quick Wins & Code Quality
**Priority:** High impact, low effort
**Affects:** `src/jetsam/platforms/base.py`, `github.py`, `gitlab.py`

## Problem

`PlatformError` is defined independently at the bottom of both `github.py` (line 263)
and `gitlab.py` (line 279) as separate, unrelated exception classes. If a caller catches
one, it won't catch the other. If executor code catches `PlatformError` from a generic
platform reference, it depends on which module was imported.

## Solution

1. Move `PlatformError` to `platforms/base.py` alongside the abstract `Platform` class
2. Import it from `base.py` in both `github.py` and `gitlab.py`
3. Remove the duplicate definitions

```python
# base.py (add at bottom)
class PlatformError(Exception):
    """Raised when a platform operation fails."""
```

```python
# github.py / gitlab.py
from jetsam.platforms.base import CheckResult, IssueDetails, Platform, PRDetails, PlatformError
```

## Acceptance Criteria

- [ ] Single `PlatformError` definition in `base.py`
- [ ] Both adapters import from `base.py`
- [ ] `from jetsam.platforms.base import PlatformError` works for callers
- [ ] Re-export from `platforms/__init__.py` for convenience
- [ ] All existing tests pass

## Estimated Scope

~10 lines changed across 3 files.
