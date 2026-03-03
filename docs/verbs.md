# Verb reference

Jetsam commands are organized into workflow verbs (plannable, state-aware
operations) and inspection verbs (read-only queries).

## Overview

| Verb | Alias | Description |
|---|---|---|
| [`status`](#status) | `s` | Show repository state snapshot |
| [`save`](#save) | `v` | Stage and commit with smart defaults |
| [`sync`](#sync) | `y` | Fetch, rebase/merge, and push |
| [`ship`](#ship) | `h` | Full pipeline: stage, commit, push, open PR |
| [`switch`](#switch) | `w` | Switch branches with automatic stash/unstash |
| [`start`](#start) | `b` | Start work on an issue or feature |
| [`finish`](#finish) | `f` | Merge PR and clean up branch |
| [`tidy`](#tidy) | `t` | Prune merged branches and stale refs |
| [`release`](#release) | `r` | Tag, push, and create platform release |
| [`log`](#log) | `l` | Condensed commit history |
| [`diff`](#diff) | `d` | Show diff with smart defaults |
| [`pr`](#pr) | `p` | Pull request operations |
| [`prs`](#prs) | — | List PRs with status |
| [`checks`](#checks) | `c` | CI check status |
| [`issues`](#issues) | `i` | List issues |
| [`init`](#init) | — | Initialize jetsam |

### Common flags

All workflow verbs support:

- `--dry-run` — show plan without executing
- `--execute` — execute without interactive confirmation
- `--json` (global) — output as JSON

---

## Workflow verbs

These verbs build plans, show previews, and execute multi-step operations.

(status)=
### status

Show repository state snapshot.

```bash
jetsam status
```

Returns: branch, upstream tracking, ahead/behind counts, staged/unstaged/untracked
files, stash count, and PR details if available.

```
  On feature-branch  (↑2, ↓1 vs origin/feature-branch)
  Staged:    src/new.py
  Modified:  src/existing.py
  Untracked: scratch.txt
  PR #42: open  checks: passing
```

(save)=
### save

Stage and commit with smart defaults.

```bash
jetsam save [-m MESSAGE] [--include GLOB] [--exclude GLOB] [FILES...]
```

**Arguments:**

: `FILES` — Optional explicit file paths to stage.

**Options:**

: `-m, --message` — Commit message. Auto-generated from file paths if omitted.
: `--include` — Glob pattern to filter which files to stage.
: `--exclude` — Glob pattern to exclude files from staging.

**Behavior:**

- Without `FILES` or `--include`, stages modified tracked files (not untracked)
- With `--include`, stages matching files from both unstaged and untracked
- Already-staged files are always included in the commit

**Examples:**

```bash
# Stage modified files and commit
jetsam save -m "fix parser bug"

# Stage specific files
jetsam save src/parser.py tests/test_parser.py -m "fix parser"

# Stage only Python files
jetsam save --include "*.py" -m "update code"

# Stage everything except tests
jetsam save --include "*" --exclude "tests/*" -m "update"
```

(sync)=
### sync

Fetch from upstream, rebase or merge, and push.

```bash
jetsam sync [--strategy rebase|merge]
```

**Options:**

: `--strategy` — Sync strategy. Defaults to `rebase` on feature branches,
  `merge` on the default branch.

**Behavior:**

- Stashes dirty changes automatically before syncing, restores after
- On feature branches: rebases onto upstream (or `origin/<default>` if no upstream)
- On the default branch: merges from upstream
- Pushes after sync if there are local commits

**Example:**

```bash
# Default: rebase on feature, merge on main
jetsam sync

# Force merge strategy
jetsam sync --strategy merge
```

(ship)=
### ship

Full pipeline: stage, commit, push, and open a PR.

```bash
jetsam ship [-m MESSAGE] [--to BRANCH] [--no-pr] [--merge]
            [--include GLOB] [--exclude GLOB]
```

**Options:**

: `-m, --message` — Commit message and PR title.
: `--to` — Target branch for PR (default: main/master).
: `--no-pr` — Skip PR creation.
: `--merge` — Also merge the PR after creating it.
: `--include` — Glob pattern for files to stage.
: `--exclude` — Glob pattern to exclude files.

**Behavior:**

- Stages files (same logic as `save`)
- Commits with the provided message
- Pushes to the remote (sets upstream if needed)
- Creates a new PR, or notes the existing one was updated via push
- Optionally merges the PR

**Examples:**

```bash
# Ship everything with a message
jetsam ship -m "add dark mode"

# Ship without creating a PR
jetsam ship -m "update config" --no-pr

# Ship and immediately merge
jetsam ship -m "hotfix" --merge

# Ship to a specific branch
jetsam ship -m "backport" --to release/v2
```

(switch)=
### switch

Switch branches with automatic stash/unstash.

```bash
jetsam switch BRANCH [-c/--create]
```

**Arguments:**

: `BRANCH` — Target branch to switch to.

**Options:**

: `-c, --create` — Create the branch if it doesn't exist.

**Behavior:**

- If the working tree is dirty, automatically stashes changes before switching
  and pops the stash on the target branch

**Example:**

```bash
jetsam switch main
jetsam switch -c new-feature
```

(start)=
### start

Start work on an issue or feature.

```bash
jetsam start TARGET [-w/--worktree] [--base BRANCH] [--prefix PREFIX]
```

**Arguments:**

: `TARGET` — Issue number (e.g. `42`) or branch name (e.g. `fix-parser`).

**Options:**

: `-w, --worktree` — Create a git worktree instead of switching branches.
: `--base` — Base branch to create from (default: main/master).
: `--prefix` — Branch name prefix (e.g. `feature/`).

**Behavior:**

- If `TARGET` is numeric, fetches the issue title from GitHub/GitLab and
  generates a branch name slug (e.g. `42-fix-parser-bug`)
- If `TARGET` is a name, uses it directly as the branch name
- In worktree mode, creates a new worktree in `.worktrees/<branch>`
- In branch mode, stashes dirty changes before switching

**Examples:**

```bash
# Start from issue number (fetches title for branch name)
jetsam start 42

# Start with explicit branch name
jetsam start fix-parser

# Start in a worktree for parallel work
jetsam start 42 --worktree

# Use a branch prefix
jetsam start fix-it --prefix feature/
```

(finish)=
### finish

Merge PR and clean up the current branch.

```bash
jetsam finish [--strategy squash|merge|rebase] [--no-delete]
```

**Options:**

: `--strategy` — Merge strategy (default: `squash`).
: `--no-delete` — Keep the branch after merging.

**Behavior:**

- Merges the PR for the current branch (if one exists)
- Switches back to the default branch (or removes the worktree if in one)
- Fetches to update refs
- Deletes the feature branch (unless `--no-delete`)

**Example:**

```bash
jetsam finish
jetsam finish --strategy rebase --no-delete
```

(tidy)=
### tidy

Clean up merged branches and stale remote refs.

```bash
jetsam tidy
```

**Behavior:**

- Prunes remote-tracking branches that no longer exist on the server
- Deletes local branches whose upstream is gone (merged and deleted remotely)
- Prunes stale worktree references (if worktrees are in use)

(release)=
### release

Tag, push the tag, and create a platform release.

```bash
jetsam release TAG [--title TITLE] [--notes NOTES] [--draft]
```

**Arguments:**

: `TAG` — Tag name (e.g. `v0.1.0`).

**Options:**

: `--title` — Release title (defaults to tag name).
: `--notes` — Release notes text.
: `--draft` — Create as a draft release.

**Behavior:**

- Creates an annotated git tag (skipped if tag already exists)
- Pushes the tag to the remote
- Creates a GitHub/GitLab release
- Warns if the working tree is dirty or not on the default branch

**Examples:**

```bash
jetsam release v0.1.0
jetsam release v0.2.0 --title "Version 0.2.0" --notes "Bug fixes and improvements"
jetsam release v1.0.0-rc1 --draft
```

---

## Inspection verbs

These verbs are read-only and do not create plans.

(log)=
### log

Show condensed commit history.

```bash
jetsam log [-n COUNT] [--branch BRANCH]
```

**Options:**

: `-n, --count` — Number of commits to show (default: 10).
: `--branch` — Branch to show log for (default: current).

(diff)=
### diff

Show diff with smart defaults.

```bash
jetsam diff [--target REF] [--stat] [--staged]
```

**Options:**

: `--target` — Diff target ref (default: working tree changes).
: `--stat` — Show only stat summary.
: `--staged` — Show staged changes instead of unstaged.

(pr)=
### pr

Pull request operations.

```bash
# View PR for current branch
jetsam pr

# Create a new PR
jetsam pr create [-t TITLE] [-b BODY] [--base BRANCH] [--draft]

# List PRs
jetsam pr list [--state open|closed|merged|all] [--author USER]
```

(prs)=
### prs

List pull requests with check and review status.

```bash
jetsam prs [--state open|closed|merged|all] [--author USER]
```

(checks)=
### checks

Show CI check status for the current branch or a specific PR.

```bash
jetsam checks [--pr NUMBER]
```

(issues)=
### issues

List issues from the project's issue tracker.

```bash
jetsam issues [--state open|closed|all] [--label LABEL]
```

---

## Setup verbs

(init)=
### init

Initialize jetsam in the current repository.

```bash
jetsam init [--mcp] [--aliases]
```

**Options:**

: `--mcp` — Add jetsam MCP server entry to `.mcp.json` (merges with existing file).
: `--aliases` — Install shell aliases to your shell config.

See [Getting started](getting-started.md) for details.
