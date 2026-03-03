# jetsam

[![PyPI](https://img.shields.io/pypi/v/jetsam)](https://pypi.org/project/jetsam/)
[![Docs](https://readthedocs.org/projects/jetsam/badge/?version=latest)](https://jetsam.readthedocs.io)
[![CI](https://github.com/teaguesterling/jetsam/actions/workflows/ci.yml/badge.svg)](https://github.com/teaguesterling/jetsam/actions)

Git workflow accelerator for humans and agents.

Jetsam wraps common multi-step git workflows into single, plannable commands. Every
action generates a preview plan before executing, making it safe for interactive use
and ideal for AI agent integration via MCP.

**[Documentation](https://jetsam-mcp.readthedocs.io)** | **[PyPI](https://pypi.org/project/jetsam-mcp/)** | **[GitHub](https://github.com/teaguesterling/jetsam)**

## Installation

```bash
pip install jetsam
# or
uv pip install jetsam
```

## Quick start

```bash
# Initialize in a repo
jetsam init

# Check status
jetsam status

# Stage + commit
jetsam save -m "fix parser bug"

# Full pipeline: stage → commit → push → PR
jetsam ship -m "add dark mode"

# Tag and release
jetsam release v0.1.0 --title "First release"
```

Every command shows a plan and asks for confirmation before executing.
Use `--dry-run` to preview without executing, or `--execute` to skip the prompt.

## Verb reference

| Verb | Alias | Description |
|---|---|---|
| `status` | `s` | Show repository state snapshot |
| `save` | `v` | Stage and commit with smart defaults |
| `sync` | `y` | Fetch, rebase/merge, and push |
| `ship` | `h` | Full pipeline: stage, commit, push, open PR |
| `switch` | `w` | Switch branches with automatic stash/unstash |
| `start` | `b` | Start work on an issue or feature (branch or worktree) |
| `finish` | `f` | Merge PR and clean up branch |
| `tidy` | `t` | Prune merged branches and stale remote refs |
| `release` | `r` | Tag, push tag, and create platform release |
| `log` | `l` | Condensed commit history |
| `diff` | `d` | Show diff with smart defaults |
| `pr` | `p` | Pull request operations (view/create/list) |
| `prs` | — | List PRs with check and review status |
| `checks` | `c` | Show CI check status |
| `issues` | `i` | List issues from project tracker |
| `init` | — | Initialize jetsam in a repo |

### Common flags

All workflow verbs (`save`, `sync`, `ship`, `switch`, `start`, `finish`, `tidy`, `release`) support:

- `--dry-run` — show plan without executing
- `--execute` — execute without prompting
- `--json` (global) — output as JSON

### Key verb options

**save** `[-m MESSAGE] [--include GLOB] [--exclude GLOB] [FILES...]`

**ship** `[-m MESSAGE] [--to BRANCH] [--no-pr] [--merge] [--include GLOB] [--exclude GLOB]`

**sync** `[--strategy rebase|merge]`

**switch** `BRANCH [-c/--create]`

**start** `TARGET [-w/--worktree] [--base BRANCH] [--prefix PREFIX]`

**finish** `[--strategy squash|merge|rebase] [--no-delete]`

**release** `TAG [--title TITLE] [--notes NOTES] [--draft]`

## MCP integration

Jetsam includes a built-in MCP server for agent integration:

```bash
# Start the MCP server
jetsam serve

# Or initialize with .mcp.json
jetsam init --mcp
```

This creates `.mcp.json` in the repo root for automatic discovery by Claude Code
and other MCP-aware tools. The MCP tools mirror CLI verbs with a plan → confirm flow:

1. Call a workflow tool (e.g. `save`, `ship`, `release`) — returns a plan
2. Optionally call `modify_plan` to adjust the plan
3. Call `confirm` to execute, or `cancel` to discard

## Shell aliases

Install short aliases for common operations:

```bash
jetsam init --aliases
```

This adds the following aliases to your shell config:

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

## Worktree support

Jetsam supports git worktrees for parallel development:

```bash
# Start work in a new worktree
jetsam start my-feature --worktree

# Finish and clean up the worktree
jetsam finish
```

### Shared paths

Create a `.git-worktree-shared` file in the repo root to automatically symlink
paths into new worktrees (one path per line):

```
.env
node_modules
.venv
```

Lines starting with `#` are ignored.

## Configuration

Jetsam stores its configuration in `.jetsam/` at the repo root:

| Path | Purpose |
|---|---|
| `.jetsam/` | Config directory (created by `init`) |
| `.jetsam/plans/` | Temporary plan storage (5-minute TTL) |
| `.mcp.json` | MCP server config (created by `init --mcp`) |
| `.git-worktree-shared` | Paths to symlink into worktrees |

## Platform support

Jetsam auto-detects GitHub and GitLab from remote URLs:

- **GitHub** — uses [gh CLI](https://cli.github.com/)
- **GitLab** — uses [glab CLI](https://gitlab.com/gitlab-org/cli)

Git pass-through: any unrecognized command is forwarded to git, so `jetsam log --oneline`
works exactly like `git log --oneline`.

## License

MIT
