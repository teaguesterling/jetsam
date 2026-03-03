# Getting started

## Installation

Install from PyPI:

```bash
pip install jetsam
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install jetsam
```

### Requirements

- Python 3.10+
- git
- [gh CLI](https://cli.github.com/) (for GitHub operations) or [glab CLI](https://gitlab.com/gitlab-org/cli) (for GitLab)

## Initialize

Run `init` in any git repository:

```bash
cd your-repo
jetsam init
```

This creates the `.jetsam/` directory for plan storage and detects your platform
(GitHub or GitLab) from the remote URL.

### MCP server setup

To use jetsam with Claude Code or other MCP-aware agents:

```bash
jetsam init --mcp
```

This adds the jetsam MCP server entry to `.mcp.json` in your repo root. If the
file already exists, jetsam merges its entry without overwriting other servers.

The generated config:

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

### Shell aliases

Install short aliases for faster access:

```bash
jetsam init --aliases
```

This appends aliases to your shell config (`~/.bashrc`, `~/.zshrc`, or
`~/.config/fish/conf.d/jetsam.fish`):

| Alias | Command |
|---|---|
| `jt` | `jetsam` |
| `jts` | `jetsam status` |
| `jtv` | `jetsam save` |
| `jty` | `jetsam sync` |
| `jth` | `jetsam ship` |
| `jtp` | `jetsam ship --pr` |
| `jtw` | `jetsam switch` |
| `jtl` | `jetsam log` |
| `jtd` | `jetsam diff` |

The aliases are guarded by a marker comment, so running `init --aliases` again
is safe — it won't duplicate them.

You can also combine flags:

```bash
jetsam init --mcp --aliases
```

## First workflow

A typical development cycle:

```bash
# Check where you are
jetsam status

# Start work on a feature
jetsam start fix-parser

# Make changes, then save (stage + commit)
jetsam save -m "fix parser edge case"

# Ship it (push + open PR)
jetsam ship

# When the PR is approved, finish (merge + cleanup)
jetsam finish
```

## The plan-confirm pattern

Every mutating command follows the same pattern:

1. **Build state** — jetsam snapshots the repo (branch, dirty files, ahead/behind, PR status)
2. **Generate plan** — based on the state and your intent, jetsam creates a step-by-step plan
3. **Show plan** — you see exactly what will happen before anything changes
4. **Confirm** — you approve or abort
5. **Execute** — steps run sequentially; execution stops on first failure

```
$ jetsam ship -m "add feature"

  Ship: add feature
  ──────────────────────────────
  Stage: src/feature.py, tests/test_feature.py (2 files)
  Commit: "add feature"
  Push: origin/feature-branch
  PR: Create → main

  [c]onfirm / [a]bort: c

  ✓ Staged 2 files
  ✓ Committed: add feature (a1b2c3d)
  ✓ Pushed to origin/feature-branch
  ✓ PR #42 created: https://github.com/user/repo/pull/42
```

### Skipping confirmation

For scripts or when you're confident:

```bash
# Execute immediately
jetsam save -m "quick fix" --execute

# Preview only (no execution)
jetsam ship -m "feature" --dry-run

# JSON output (also skips interactive prompt)
jetsam --json ship -m "feature"
```

## Entry points

Jetsam installs two CLI entry points:

- `jetsam` — full name
- `jt` — short alias

Both are identical. Use whichever you prefer.

## Git pass-through

Any command jetsam doesn't recognize is forwarded to git:

```bash
jetsam rebase -i HEAD~3    # → git rebase -i HEAD~3
jetsam stash list          # → git stash list
jetsam cherry-pick abc123  # → git cherry-pick abc123
```

This means you never need to switch between `jetsam` and `git` — use jetsam for
everything and it handles the routing.
