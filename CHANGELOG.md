# Changelog

## v0.1.0

Initial release.

### Core workflow verbs
- **status** — repository state snapshot
- **save** — stage and commit with smart defaults
- **sync** — fetch, rebase/merge, and push
- **ship** — full pipeline: stage, commit, push, open PR

### Navigation verbs
- **switch** — stash-aware branch switching
- **start** — begin work on an issue or feature (branch or worktree)
- **finish** — merge PR and clean up branch/worktree
- **tidy** — prune merged branches and stale remote refs

### Inspection verbs
- **log** — condensed commit history
- **diff** — diff with smart defaults
- **pr** — PR operations (view/create/list)
- **prs** — list PRs with check and review status
- **checks** — CI check status
- **issues** — list issues from project tracker

### Release
- **release** — tag, push tag, and create platform release

### Platform support
- GitHub (via `gh` CLI)
- GitLab (via `glab` CLI)

### Agent integration
- Built-in MCP server with plan → confirm flow
- `init --mcp` generates `.mcp.json` for Claude Code discovery

### Developer experience
- Shell alias installation (`init --aliases`)
- Shell completions for bash, zsh, fish
- Worktree shared paths (`.git-worktree-shared`)
- Error recovery suggestions on common failures
- Git pass-through for unrecognized commands
