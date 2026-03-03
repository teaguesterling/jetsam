# P8-003: Add Structured Logging

**Phase:** 8 — Testing & Polish
**Priority:** Low-medium impact, moderate effort
**Affects:** Multiple source files

## Problem

The codebase uses `click.echo()` exclusively for output. There is no `logging` module
usage anywhere. This creates problems for:

1. **MCP server debugging** — stdout is the MCP transport, so any debug output
   corrupts the protocol. There's no way to get diagnostic output from the server.
2. **CI debugging** — when tests fail or behavior is unexpected, there's no trace
   of what git commands were run or what state was detected.
3. **User debugging** — when a plan fails, users have no verbose mode to see
   what happened internally.

## Solution

### Step 1: Add logging to key modules

```python
import logging

logger = logging.getLogger(__name__)
```

**Where to log:**

| Module | What to log | Level |
|---|---|---|
| `git/wrapper.py` | Git commands run and their exit codes | DEBUG |
| `core/state.py` | State snapshot contents | DEBUG |
| `core/executor.py` | Step execution start/end, results | DEBUG |
| `core/planner.py` | Plan generation decisions | DEBUG |
| `core/plans.py` | Plan save/load/expire events | DEBUG |
| `platforms/*.py` | Platform CLI commands and responses | DEBUG |
| `config/manager.py` | Config file locations and merge | DEBUG |

### Step 2: Add --verbose flag to CLI

```python
@click.group(cls=JetsamGroup)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(ctx, json_output, verbose):
    if verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
```

Key: logging goes to stderr, never stdout. This keeps JSON output and MCP
transport clean.

### Step 3: Configure logging for MCP server

```python
# mcp/server.py
def serve_stdio():
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(name)s %(levelname)s: %(message)s",
    )
```

The MCP server defaults to WARNING level (quiet), but can be configured
via environment variable:

```bash
JETSAM_LOG_LEVEL=debug jetsam serve
```

## Acceptance Criteria

- [ ] `logging` module used in all core modules
- [ ] All log output goes to stderr (never stdout)
- [ ] `jetsam -v status` shows debug output
- [ ] MCP server doesn't pollute stdout with log messages
- [ ] Log format includes module name and level
- [ ] `JETSAM_LOG_LEVEL` environment variable supported
- [ ] No performance impact when logging is disabled (lazy formatting)

## Estimated Scope

~5-10 lines per module (8 modules = ~60-80 lines total). CLI flag ~5 lines.
No changes to existing behavior when verbose is off.

## Notes

Use lazy string formatting to avoid performance impact:

```python
# Good (no formatting cost if DEBUG disabled)
logger.debug("Running git %s", args)

# Bad (always formats)
logger.debug(f"Running git {args}")
```

## Dependencies

None.
