# P5-003: Add py.typed Marker

**Phase:** 5 — Quick Wins & Code Quality
**Priority:** High impact, low effort
**Affects:** `src/jetsam/`

## Problem

The package uses strict mypy and has comprehensive type annotations, but doesn't ship
a `py.typed` marker file (PEP 561). Downstream consumers who import jetsam modules
can't benefit from the type annotations because mypy/pyright won't recognize the
package as typed.

## Solution

Create an empty `py.typed` file in the package root:

```bash
touch src/jetsam/py.typed
```

Verify it's included in the wheel by checking `hatch build` output.

## Acceptance Criteria

- [ ] `src/jetsam/py.typed` exists (empty file)
- [ ] File is included in built wheel
- [ ] mypy continues to pass

## Estimated Scope

1 new file.
