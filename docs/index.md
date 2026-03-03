# jetsam

**Git workflow accelerator for humans and agents.**

Jetsam wraps common multi-step git workflows into single, plannable commands.
Every action generates a preview plan before executing, making it safe for
interactive use and ideal for AI agent integration via MCP.

```bash
# Stage, commit, push, and open a PR — one command
jetsam ship -m "add dark mode"

# Preview what would happen without doing it
jetsam ship -m "add dark mode" --dry-run
```

## Why jetsam?

**For developers:** Replace repetitive multi-step git sequences with single
commands that check state, show a plan, and ask before acting.

**For AI agents:** Structured JSON output and an MCP server interface eliminate
the need to parse verbose git text output. The plan-confirm pattern gives agents
safe, auditable git operations.

**For teams:** A consistent abstraction over both GitHub and GitLab means the
same commands work regardless of platform.

## Key features

- **Plannable operations** — every mutating command shows what it will do before doing it
- **State-aware** — checks branch, dirty state, ahead/behind, existing PRs before acting
- **Dual interface** — same operations via CLI and MCP server
- **Platform-agnostic** — GitHub (`gh`) and GitLab (`glab`) behind a unified interface
- **Git pass-through** — unrecognized commands forward to git, so `jetsam rebase -i HEAD~3` just works
- **Error recovery** — failed steps include suggested fixes

## Quick links

```{toctree}
:maxdepth: 2

getting-started
verbs
mcp
configuration
changelog
```
