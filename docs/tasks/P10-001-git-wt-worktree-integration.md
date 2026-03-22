# P10-001: Replace git-wt with Jetsam Worktree Support

**Phase:** 10 — Worktree Workflow
**Priority:** Medium
**Affects:** `src/jetsam/core/executor.py`, `src/jetsam/worktree/`, `src/jetsam/cli/verbs/start.py`, new verbs

## Context

The user has a `git-wt` bash script (~1200 lines) at `~/.dotfiles/git-wt/git-wt.sh`
that provides a full worktree workflow. Jetsam has basic worktree support via
`start --worktree` and `finish`, but git-wt has significantly more features.

## Features in git-wt Not in Jetsam

### Directory structure
git-wt restructures repos into `project/main/` + `project/trees/` (siblings).
Jetsam uses `.worktrees/<branch>` inside the repo. The `worktree_dir` config
option (added in v0.3.0) makes this configurable, but doesn't support the
`main/` + `trees/` sibling layout with marker file detection.

### Worktree lifecycle
- **resume** — `cd` to an existing worktree (interactive selection if ambiguous)
- **back** — return to main worktree
- **cancel** — remove worktree without cleanup (no push, no PR, no branch delete)
- **delete** — interactive selection + finish semantics

### Robustness
- **LFS support** — `GIT_LFS_SKIP_SMUDGE=1` during worktree creation, then `git lfs pull`
- **Stale worktree recovery** — prunes stale entry then re-creates
- **Uncommitted change check** — excludes shared paths from dirty detection
- **Submodule auto-detection** — adds initialized submodules to shared paths config

### Interactive features
- Menu-based worktree selection when multiple match a filter
- Confirmation prompts for destructive operations

## Design Questions

1. Should jetsam adopt the `main/` + `trees/` sibling layout, or keep worktrees
   inside the repo with configurable `worktree_dir`?
2. Which git-wt features are needed for MCP/agent use vs. human-only CLI?
3. Should `resume` and `back` be jetsam verbs or stay as shell functions
   (they need to change the shell's working directory)?

## Acceptance Criteria

- [ ] Jetsam can replace git-wt for the user's daily workflow
- [ ] LFS-aware worktree creation
- [ ] Stale worktree detection and recovery
- [ ] Shared paths exclude from dirty checks
- [ ] Submodule auto-detection for shared paths
- [ ] Config option for worktree layout style

## Estimated Scope

Needs a full design spec (brainstorming session). Estimated 2-3 days of
implementation after design.
