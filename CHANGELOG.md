# Changelog

## v0.3.0

Rollup release consolidating agent adoption improvements and bug fixes.
See v0.2.0 and v0.2.1 entries below for details.

## v0.2.1

### Bug fixes
- `ship` with explicit `files` parameter now scopes staging exclusively (#4)
- `ship` skips commit step when nothing to commit, proceeds to push/PR (#7)
- `save` returns empty plan with warning when nothing to save (#7)
- `_resolve_files` applies `exclude` filter to explicit file lists (#4)

### New
- MCP `ship()` tool accepts `files` parameter for scoped staging

## v0.2.0

### New MCP tools
- **pr_comment** — post a comment on a pull request
- **pr_review** — submit a PR review (approve, request-changes, comment)
- **pr_comments** — read comments and reviews on a PR
- **issue_close** — close an issue with optional comment and reason

### Agent adoption improvements
- `init --agents claude|gemini|agents|none|<path>` — generate agent instruction
  files (CLAUDE.md, GEMINI.md, etc.) with JetSam routing table
- `init --hooks claude|none` — generate Claude Code warning hooks that alert
  agents when they use raw git/gh commands instead of JetSam tools

### Bug fixes
- Fix stash_pop failure when nothing was stashed (#5)
- Fix stale plan error when fetch changes repo state (#2)
- Simplify sync plan on default branch — fast path for push-only (#3)

### Developer experience
- Resolve all mypy strict errors (14 → 0)
- Type `_get_platform` return as `Platform | None` instead of `Any`

## v0.1.1

- Document `auto_push` and `commit_message` configuration options
- Fix `init --mcp` to merge into existing `.mcp.json` instead of overwriting
- Add Sphinx documentation for ReadTheDocs

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
