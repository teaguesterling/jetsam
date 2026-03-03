# MCP integration

Jetsam includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/)
server, making it usable as a tool provider for AI agents like Claude Code.

## Setup

### Automatic (recommended)

```bash
jetsam init --mcp
```

This adds the jetsam server entry to `.mcp.json` in your repo root. If the file
already has other MCP servers configured, jetsam merges its entry without
overwriting them.

### Manual

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "jetsam": {
      "command": "jetsam",
      "args": ["serve"],
      "type": "stdio"
    }
  }
}
```

Or start the server directly:

```bash
# stdio transport (default, for Claude Code)
jetsam serve

# SSE transport (for HTTP-based clients)
jetsam serve --transport sse
```

## Tool reference

### Workflow tools (plan-based)

These tools return a plan that must be confirmed before execution.
The workflow is: **call tool** → **inspect/modify plan** → **confirm or cancel**.

| Tool | Description |
|---|---|
| `save` | Stage and commit changes |
| `sync` | Fetch, rebase/merge, push |
| `ship` | Stage, commit, push, open PR |
| `switch` | Switch branches (stash-aware) |
| `start` | Begin work on issue/feature |
| `finish` | Merge PR and clean up |
| `tidy` | Prune merged branches |
| `release` | Tag, push tag, create release |

### Plan management tools

| Tool | Description |
|---|---|
| `show_plan` | Inspect a plan before confirming |
| `modify_plan` | Change commit message or exclude files |
| `confirm` | Execute a plan |
| `cancel` | Discard a plan |

### Inspection tools (immediate)

These tools return results directly without creating plans.

| Tool | Description |
|---|---|
| `status` | Repository state snapshot |
| `log` | Commit history |
| `diff` | Diff (stat or full) |
| `pr_view` | PR details for a branch |
| `pr_list` | List pull requests |
| `checks` | CI check status |
| `issues` | List issues |
| `git` | Pass-through any git command |

## Agent workflow example

A typical agent interaction using jetsam MCP tools:

```
Agent                              Jetsam
  │                                   │
  ├─ status() ───────────────────────>│
  │<──── {branch, dirty, staged, ...} │
  │                                   │
  ├─ save(message="fix bug") ────────>│
  │<──── {plan_id: "p_abc123",        │
  │       steps: [stage, commit],     │
  │       warnings: [...]}            │
  │                                   │
  ├─ confirm(id="p_abc123") ─────────>│
  │<──── {status: "ok",               │
  │       results: [{step: "stage",   │
  │                  ok: true}, ...]}  │
```

### Plan lifecycle

Plans have a **5-minute TTL**. If not confirmed within 5 minutes, they expire
and must be regenerated. This prevents stale plans from executing against a
changed repository state.

Before execution, jetsam validates that the repository state hash matches the
hash recorded when the plan was created. If the repo has changed (new commits,
staged files, etc.), execution fails with a `stale_plan` error and a suggestion
to re-run the command.

### Modifying plans

Plans can be adjusted before confirmation:

```json
// Change the commit message
{"tool": "modify_plan", "params": {"id": "p_abc123", "message": "better message"}}

// Remove files from staging
{"tool": "modify_plan", "params": {"id": "p_abc123", "exclude": "*.log"}}
```

The response includes a `diff` showing what changed.

### Error handling

All errors are returned as structured objects:

```json
{
  "error": "plan_not_found",
  "message": "Plan p_abc123 not found or expired.",
  "suggested_action": "Re-run the original command.",
  "recoverable": true
}
```

Step failures include recovery suggestions:

| Failure | Suggestion |
|---|---|
| Push rejected | `sync` (pull/rebase first) |
| Rebase conflict | Resolve conflicts, then `git rebase --continue` |
| Checkout blocked by dirty state | `save` or stash changes first |
| Tag already exists | Delete existing tag first |

### Pass-through

The `git` tool provides a raw escape hatch for any git operation not covered
by workflow tools:

```json
{"tool": "git", "params": {"args": ["rebase", "--abort"]}}
```

Returns `{ok, stdout, stderr, returncode}`.
