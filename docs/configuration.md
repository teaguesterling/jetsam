# Configuration

## File locations

| Path | Purpose |
|---|---|
| `.jetsam/` | Per-repo config directory (created by `init`) |
| `.jetsam/config.yaml` | Per-repo configuration |
| `.jetsam/plans/` | Temporary plan storage (5-minute TTL, auto-cleaned) |
| `~/.config/jetsam/config.yaml` | Global user configuration |
| `.mcp.json` | MCP server config (created by `init --mcp`) |
| `.git-worktree-shared` | Paths to symlink into new worktrees |

## Configuration options

Configuration is loaded from YAML files. Per-repo config (`.jetsam/config.yaml`)
overrides global config (`~/.config/jetsam/config.yaml`).

```yaml
# .jetsam/config.yaml

# Platform detection: auto | github | gitlab
platform: auto

# Default merge strategy for finish: squash | merge | rebase
merge_strategy: squash

# Ship default behavior: pr | merge
ship_default: pr

# Create PRs as drafts by default
pr_draft: false

# Branch name prefix for start verb
branch_prefix: ""

# Delete branch after merge in finish
delete_on_merge: true

# Automatically push after save: true | false
auto_push: false

# Worktree usage: auto | always | never
worktree: auto

# Commit message strategy: heuristic | prompt | llm
commit_message: heuristic
```

### Option reference

`platform`
: Platform to use for PR/issue operations. Set to `auto` (default) to detect
  from the remote URL. Set explicitly if auto-detection fails.

`merge_strategy`
: Default strategy for `finish`. One of `squash` (default), `merge`, or `rebase`.

`ship_default`
: What `ship` does by default. `pr` creates/updates a PR, `merge` also merges it.

`pr_draft`
: When `true`, PRs are created as drafts by default.

`branch_prefix`
: Prefix prepended to branch names created by `start`. For example,
  `feature/` would create branches like `feature/42-fix-parser`.

`delete_on_merge`
: Whether `finish` deletes the branch after merging. Default: `true`.

`auto_push`
: When `true`, `save` automatically pushes after committing. Default: `false`.

`worktree`
: Worktree mode for `start`. `auto` (default) uses branches normally.
  `always` creates worktrees by default. `never` disables worktree creation.

`commit_message`
: Strategy for generating commit messages. `heuristic` (default) builds a message
  from the staged changes. `prompt` asks interactively. `llm` delegates to an LLM.
  *Reserved — not yet implemented.*

## Platform support

Jetsam auto-detects your platform from the git remote URL:

- **GitHub** — uses [gh CLI](https://cli.github.com/)
- **GitLab** — uses [glab CLI](https://gitlab.com/gitlab-org/cli)

The platform CLI must be installed and authenticated. Jetsam calls these tools
as subprocesses and parses their output.

### Verifying platform setup

```bash
# Check if platform is detected
jetsam status
# Look for "platform" in JSON output:
jetsam --json status | python -m json.tool
```

## Worktree shared paths

When using `jetsam start --worktree`, you often want certain files or directories
shared across all worktrees (`.env` files, `node_modules`, virtual environments).

Create a `.git-worktree-shared` file in the repo root:

```
# Shared across all worktrees
.env
.env.local
node_modules
.venv
```

When a new worktree is created via `jetsam start --worktree`, each listed path
is symlinked from the main repo into the worktree. This happens automatically —
no extra flags needed.

Rules:
- One path per line
- Lines starting with `#` are comments
- Blank lines are ignored
- Missing source paths are silently skipped
- Existing files/symlinks in the worktree are not overwritten

## JSON output

All commands support JSON output via the global `--json` flag:

```bash
jetsam --json status
jetsam --json save -m "fix"
jetsam --json ship --dry-run
```

This is useful for scripting and for the MCP server interface.
