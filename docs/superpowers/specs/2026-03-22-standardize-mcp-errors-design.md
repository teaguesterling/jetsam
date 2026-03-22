# P6-002: Standardize MCP Error Returns — Design Spec

## Problem

MCP tools return errors in at least four different formats (list-wrapped dicts,
plain dicts, ad-hoc dicts, `JetsamError`), forcing agents to handle error
detection differently per tool.

## Approach

**Approach C: JetsamError dict for expected errors + exception propagation for
unexpected failures.**

- Expected/recoverable errors (no platform, no PR, bad git ref) return
  `JetsamError.to_dict()` — a dict with `error`, `message`, `recoverable`,
  and optionally `suggested_action`.
- Unexpected failures (platform crashes, network errors) propagate as
  exceptions, caught by FastMCP and surfaced via MCP protocol `isError=True`.

### Why this approach

- Structured data for expected errors lets agents act programmatically (e.g.
  branch on `error == "no_pr"` vs `error == "no_platform"`).
- MCP `isError` alone only provides plain text — no machine-readable codes.
- Exception propagation for unexpected failures is the correct semantic — agents
  can't recover from those anyway.

## Error Contract

All expected error responses use `JetsamError.to_dict()`:

```python
{
    "error": "<error_code>",       # machine-readable, always present
    "message": "<human-readable>", # always present
    "recoverable": True|False,     # always present
    "suggested_action": "..."      # optional, only present when provided
}
```

Note: `JetsamError.to_dict()` omits `suggested_action` when it is `None`,
so not all error dicts will have this key.

Agents detect errors via:
- Dict-returning tools: `if "error" in response`
- List-returning tools: `if isinstance(response, dict) and "error" in response`
  (success returns a list, error returns a dict)

### Standard Error Codes

| Code | Meaning |
|---|---|
| `no_platform` | No GitHub/GitLab remote configured |
| `no_pr` | No PR found for the given branch |
| `git_error` | A git command failed |
| `plan_not_found` | Plan ID is invalid or expired |

## Tool Changes

### Dict-returning tools — replace ad-hoc dicts with JetsamError

| Tool | Error Code | Message |
|---|---|---|
| `diff()` (stat mode) | `git_error` | stderr from git |
| `diff()` (full mode) | `git_error` | stderr from git (when `result.ok` is False) |
| `pr_view()` | `no_platform` | "No platform configured" |
| `pr_comment()` | `no_platform` / `no_pr` | contextual |
| `pr_review()` | `no_platform` / `no_pr` | contextual |
| `issue_close()` | `no_platform` | "No platform configured" |

### List-returning tools — return JetsamError dict instead of list-wrapped error

| Tool | Error Code(s) | Current Return | New Return |
|---|---|---|---|
| `log()` | `git_error` | `[{"error": ...}]` | `JetsamError.to_dict()` |
| `pr_list()` | `no_platform` | `[{"error": ...}]` | `JetsamError.to_dict()` |
| `checks()` | `no_platform`, `no_pr` | `[{"error": ...}]` | `JetsamError.to_dict()` |
| `issues()` | `no_platform` | `[{"error": ...}]` | `JetsamError.to_dict()` |
| `pr_comments()` | `no_platform`, `no_pr` | `[{"error": ...}]` | `JetsamError.to_dict()` |

### No changes needed

- `show_plan()`, `modify_plan()`, `confirm()` — already use `JetsamError`.
- `status()`, `save()`, `sync()`, `ship()`, `switch()`, `start()`, `finish()`,
  `tidy()`, `release()` — plan-returning/state tools. Errors propagate as
  exceptions (consistent with the exception-propagation strategy for unexpected
  failures).
- `cancel()` — no error path (silently succeeds if plan ID is missing).

### Intentionally excluded

- `git()` — raw pass-through tool. Returns `{"ok", "stdout", "stderr",
  "returncode"}` by design. Agents using this tool expect raw git output, not
  structured JetsamError responses.

## Helper Function

Introduce a module-level helper in `tools.py` to reduce repetition for the
common `no_platform` case:

```python
def _no_platform_error() -> dict[str, Any]:
    return JetsamError(
        error="no_platform",
        message="No platform configured.",
        suggested_action="Configure a GitHub or GitLab remote.",
        recoverable=False,
    ).to_dict()
```

Similarly for `no_pr`:

```python
def _no_pr_error(branch: str) -> dict[str, Any]:
    return JetsamError(
        error="no_pr",
        message=f"No PR found for branch '{branch}'.",
        recoverable=True,
    ).to_dict()
```

## MCP Server Instruction Update

Add to the `instructions` string in `server.py`:

```
"Error responses always contain 'error' and 'message' keys. "
"Check if 'error' in response to detect errors."
```

## Tests

Add/update tests in `test_mcp_tools.py` verifying:

- Each error path returns a dict (not a list) with `error` and `message` keys
- `recoverable` is always present in error responses
- Error codes match the standard set
- List-returning tools return a dict on error, a list on success

## Scope

~30-40 lines changed in `tools.py`, ~5 lines in `server.py`, ~10 new/updated
tests. No changes to `JetsamError` itself or the platform layer.
