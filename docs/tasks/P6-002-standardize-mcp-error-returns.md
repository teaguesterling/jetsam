# P6-002: Standardize MCP Error Returns

**Phase:** 6 — Config & Standardization
**Priority:** High impact, moderate effort
**Affects:** `src/jetsam/mcp/tools.py`, `src/jetsam/core/output.py`

## Problem

MCP tools return errors in at least four different formats, forcing agents to handle
error detection differently per tool:

| Tool | Error Format | Example |
|---|---|---|
| `log()` | List-wrapped dict | `[{"error": "..."}]` |
| `diff()` | Plain dict | `{"error": "..."}` |
| `pr_view()` | Custom dict | `{"error": "no_platform", "message": "..."}` |
| `pr_list()` | List-wrapped dict | `[{"error": "no_platform"}]` |
| `show_plan()` | JetsamError | `{"error": "...", "message": "...", "suggested_action": "...", "recoverable": true}` |
| `confirm()` | JetsamError | Same as above |

Agents have no consistent way to detect "is this an error response?" across tools.

## Solution

### Define a standard error contract

All MCP tools should use `JetsamError` for error responses. The error dict always has
`"error"` and `"message"` keys, plus optional `"suggested_action"` and `"recoverable"`.

### For tools returning `dict`:

```python
# Before
return {"error": result.stderr.strip()}

# After
return JetsamError(
    error="git_error",
    message=result.stderr.strip(),
    recoverable=True,
).to_dict()
```

### For tools returning `list`:

Tools that return lists should raise or return errors differently from valid results.
Options:
- Return `{"error": ..., "items": []}` (wrapper dict)
- Use MCP's error mechanism if available
- Keep list return but ensure error items have consistent shape

Recommended: tools returning lists should return an empty list on error and log/surface
the error via the MCP framework, OR wrap in a dict: `{"items": [...]}` / `{"error": "..."}`.

### Specific changes needed:

1. `log()` — return `JetsamError` dict instead of `[{"error": ...}]`
2. `diff()` — return `JetsamError` dict instead of `{"error": ...}`
3. `pr_view()` — use `JetsamError` instead of ad-hoc dict
4. `pr_list()` — return `JetsamError` dict instead of `[{"error": ...}]`
5. `checks()` — use `JetsamError` for no_platform and no_pr cases
6. `issues()` — use `JetsamError` for no_platform case

## Acceptance Criteria

- [ ] All MCP tool error responses use `JetsamError.to_dict()` format
- [ ] Error responses always have `"error"` and `"message"` keys
- [ ] Agents can check `if "error" in response` to detect errors uniformly
- [ ] List-returning tools have a consistent error pattern
- [ ] MCP tool tests updated to verify error response format
- [ ] Document the error contract in MCP server instruction string

## Estimated Scope

~30-40 lines changed in `tools.py`. ~10 new/updated tests.

## Notes

Consider whether list-returning tools should change their return type signature to
`dict` (with an `items` key) so the return type is consistent for success and error.
This is a breaking change for agents already consuming the tools, so it should be
weighed carefully.
