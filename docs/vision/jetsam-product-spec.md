# jetsam — Git Workflow Accelerator

**A git workflow accelerator for humans and agents.**

Wraps `git`, `gh`, and `glab` into composable verbs with state awareness, structured output, and a plan→confirm→execute pattern. Parallel CLI and MCP interfaces from the same codebase.

Part of a toolkit with a shared sensibility: **blq** (bleak) for build logs, **Fledgling** (struggling) for code navigation, and **jetsam** for git operations. Jetsam is cargo deliberately thrown overboard to save a sinking ship — your code is what gets jettisoned when things get desperate. The maritime metaphor maps precisely: `jetsam ship` (throw it overboard), `jetsam save` (mark where it sank), `jetsam tidy` (clear the flotsam), `jetsam sync` (check the tides). Same sardonic energy as the rest of the suite.

---

## Problem

### For agents

AI coding agents spend 30-50% of their git-related tokens on verbose, unstructured output from `git` and `gh`. A typical "ship this change" sequence requires 4+ tool calls (`git add`, `git commit`, `git push`, `gh pr create`), each producing text that must be parsed, with error handling at every step. The recent migration of `gh` to GraphQL has made this worse — agents get trapped in pagination loops and retry cycles just to answer basic questions like "is there already a PR for this branch?"

### For humans

Developers execute the same multi-step git sequences dozens of times per day. The commands are muscle memory, but the cognitive overhead of checking state between steps (Am I on the right branch? Are there uncommitted changes? Is the remote ahead? Is there already a PR?) creates friction and errors. Existing tools (lazygit, Graphite) either focus on TUI visualization or opinionated PR workflows — none provide simple composable verbs with state awareness.

### For both

`gh` and `glab` have divergent interfaces for equivalent operations. Platform-switching (GitHub↔GitLab) means relearning commands, and no tool provides a consistent abstraction over both.

---

## Solution

A Python CLI that:

1. **Provides composable workflow verbs** that chain multi-step git operations with state awareness
2. **Passes through everything else** — unknown verbs delegate to `git`/`gh`/`glab` with structured output parsing
3. **Builds mutable plans** — preview, refine, then execute; never touches the filesystem until confirm
4. **Returns structured output** — JSON for agents, human-readable summaries for terminals
5. **Abstracts platforms** — same verbs for GitHub and GitLab
6. **Exposes an MCP server** — agents call the same operations via tool interface

---

## Core Concepts

### Two Tiers: Workflow Verbs and Pass-Through

The tool has **opinions about workflows** but **no opinions about git**.

**Tier 1 — Workflow verbs** are the reason the tool exists. These are state-aware, plannable, multi-step operations: `ship`, `save`, `sync`, `start`, `finish`. They build plans, check preconditions, and execute with structured results.

**Tier 2 — Pass-through** covers everything else. Any verb the tool doesn't own gets delegated to `git` (or `gh`/`glab` for platform operations), with two enhancements:

1. **Structured output parsing** — the tool captures git's verbose text output and returns structured JSON when `--json` is requested. Agents get parseable data instead of text to grep through.
2. **State snapshot updating** — after a pass-through command completes, the tool updates its internal state so subsequent workflow verbs have accurate context.

This means users never need to context-switch. If they know `git rebase -i HEAD~3`, they can run `jetsam rebase -i HEAD~3` and get the same result with optional structured output. Zero learning curve for anything that isn't a workflow verb.

```bash
# Workflow verb — tool has opinions, builds a plan
$ jetsam ship -m "fix parser"

# Pass-through — delegates to git, parses output
$ jetsam rebase -i HEAD~3      # → git rebase -i HEAD~3
$ jetsam stash list             # → git stash list (structured if --json)
$ jetsam cherry-pick abc123     # → git cherry-pick abc123

# Pass-through to platform CLI
$ jetsam gh api ...             # → gh api ... (structured output)
$ jetsam glab ci status         # → glab ci status (structured output)
```

For MCP, pass-through is exposed as a generic `git` tool:

```json
{"tool": "git", "params": {"args": ["rebase", "-i", "HEAD~3"]}}
```

This ensures agents always have an escape hatch to raw git without leaving the structured output contract.

### State Awareness

Before any workflow verb, the tool builds a snapshot of the current repository state:

```json
{
  "branch": "fix-parser",
  "upstream": "origin/fix-parser",
  "default_branch": "main",
  "dirty": true,
  "staged": ["src/parser.py"],
  "unstaged": ["src/utils.py", "tests/test_parser.py"],
  "untracked": ["scratch.txt"],
  "ahead": 0,
  "behind": 2,
  "stash_count": 1,
  "pr": {
    "number": 42,
    "state": "open",
    "checks": "passing",
    "reviews": "approved",
    "mergeable": true
  },
  "platform": "github",
  "remote": "teaguesterling/myproject",
  "worktree": {
    "active": true,
    "root": "/home/user/projects/myapp",
    "current": "/home/user/projects/myapp/trees/fix-parser",
    "main_path": "/home/user/projects/myapp/main"
  }
}
```

This snapshot informs every operation — the tool never asks what it can figure out itself. The state is rebuilt cheaply (a few git commands) and cached for the duration of a plan.

### Mutable Plans

Every workflow verb follows a **plan → refine → confirm → execute** pattern. Plans are mutable drafts — the agent or human can adjust them before anything touches the filesystem.

**Phase 1 — Plan.** The tool analyzes state, determines steps, returns a plan with an ID.

**Phase 2 — Refine.** The plan can be modified: add/remove files, change the commit message, adjust the target branch, toggle PR creation. Each refinement returns the updated plan with a diff showing what changed.

**Phase 3 — Confirm.** Only `confirm` executes. Everything before it is pure computation against the state snapshot.

**Phase 4 — Execute.** Steps run in sequence. Each step reports its result. If a step fails, the plan halts with the failure context and what was already completed (for rollback decisions).

#### MCP Flow

```python
# Agent builds initial plan
ship(include="*.cpp", exclude="generated.cpp", message="fix parser",
     to="main", open_pr=True)
# → {
#     "plan_id": "p_7f3a",
#     "steps": [
#       {"action": "stage", "files": ["parser.cpp", "lexer.cpp", "util.cpp"]},
#       {"action": "commit", "message": "fix parser", "file_count": 3},
#       {"action": "push", "branch": "fix-parser", "remote": "origin"},
#       {"action": "pr_create", "title": "fix parser", "base": "main"}
#     ],
#     "warnings": ["lexer.cpp has unstaged changes from 3 days ago"]
#   }

# Agent decides to exclude a test file
update_plan("p_7f3a", exclude="test_parser.cpp")
# → {
#     "plan_id": "p_7f3a",
#     "steps": [
#       {"action": "stage", "files": ["parser.cpp", "util.cpp"]},
#       ...
#     ],
#     "diff": {"removed_files": ["test_parser.cpp"]}
#   }

# Agent adds header files
update_plan("p_7f3a", include="headers/*.h")
# → files list grows, diff shows additions

# Agent changes the message
update_plan("p_7f3a", message="fix parser edge case in UTF-8 handling")
# → message updated in commit step

# When satisfied
confirm("p_7f3a")
# → Executes all steps, returns structured result per step
```

#### CLI Flow

```bash
$ jetsam ship --include="*.cpp" --exclude="generated.cpp" -m "fix parser" --to=main --pr

  Ship: fix-parser → main
  ─────────────────────────
  Stage: parser.cpp, lexer.cpp, util.cpp (3 files)
  Commit: "fix parser"
  Push: origin/fix-parser
  PR: Create → main
  ⚠ lexer.cpp has unstaged changes from 3 days ago

  [e]dit / [c]onfirm / [a]bort: e

  exclude> test_parser.cpp

  Updated:
  Stage: parser.cpp, util.cpp (2 files)  [-test_parser.cpp]
  Commit: "fix parser"
  Push: origin/fix-parser
  PR: Create → main

  [e]dit / [c]onfirm / [a]bort: c

  ✓ Staged 2 files
  ✓ Committed: fix parser (abc1234)
  ✓ Pushed to origin/fix-parser
  ✓ PR #43 created: https://github.com/user/repo/pull/43
```

#### Non-interactive / Agent CLI Mode

```bash
# Dry run returns JSON plan
$ jetsam ship -m "fix" --dry-run --json
{"plan_id": "p_7f3a", "steps": [...]}

# Execute without prompting
$ jetsam ship -m "fix" --execute
{"results": [{"step": "stage", "ok": true}, ...]}
```

#### Plan Persistence

Plans are stored as temp files in `.jetsam/plans/` with a 5-minute TTL. This handles the MCP case where `ship()` and `confirm()` are separate tool calls. Plans encode the full state snapshot they were built against — if the repo state changes between plan and confirm (e.g., someone else pushed), the confirm fails with a stale-plan error and the agent must re-plan.

For the CLI interactive flow, the plan lives in-process and never hits disk.

---

## Commands

### Workflow Verbs (Tier 1)

These are the composable, state-aware, plannable operations.

#### Everyday

| Command | Description | Wraps |
|---------|-------------|-------|
| `status` | Rich state snapshot (branch, dirty, PR, checks, worktree) | `git status` + `git log` + `gh pr view` |
| `save` | Stage + commit with smart defaults | `git add` + `git commit` |
| `sync` | Pull/rebase from upstream, push local | `git fetch` + `git rebase` + `git push` |
| `ship` | Full pipeline: stage → commit → push → PR (→ merge) | All of the above |
| `pr` | Create or update PR with smart defaults | `gh pr create` / `gh pr edit` |
| `switch` | Switch branches/worktrees (stash-aware) | `git stash` + `git checkout` + `git stash pop` |

#### Lifecycle

| Command | Description |
|---------|-------------|
| `start <issue\|name>` | Create branch (or worktree) from issue, link PR when ready |
| `finish` | Merge current PR, delete branch/worktree, switch to default |
| `tidy` | Prune merged branches, clean stale remotes |
| `release <tag>` | Tag, push tag, create GitHub/GitLab release |

#### Query

| Command | Description | Wraps |
|---------|-------------|-------|
| `log` | Condensed commit history | `git log` |
| `prs` | List PRs with status/checks/reviews | `gh pr list` + `gh pr checks` |
| `issues` | List/search issues | `gh issue list` |
| `checks` | CI status for current branch or PR | `gh pr checks` |
| `diff` | Diff with smart defaults (vs main, vs upstream) | `git diff` |

### Pass-Through (Tier 2)

Any unrecognized verb is delegated:

```bash
jetsam commit -m "message"     # → git commit -m "message"
jetsam rebase -i HEAD~3        # → git rebase -i HEAD~3
jetsam stash pop               # → git stash pop
jetsam cherry-pick abc123      # → git cherry-pick abc123
jetsam blame src/main.py       # → git blame src/main.py
```

Pass-through commands:
- Run the underlying `git` command with all arguments forwarded
- Capture stdout/stderr
- Parse output into structured form when `--json` is requested
- Update the internal state snapshot after completion
- Return the raw output to the terminal by default (human mode)

For platform commands, prefix with the platform:
```bash
jetsam gh pr list              # → gh pr list
jetsam glab ci status          # → glab ci status
```

### Management

| Command | Description |
|---------|-------------|
| `init` | Detect platform, set defaults, optionally create `.mcp.json` |
| `config` | View/set preferences (merge strategy, auto-push, etc.) |
| `serve` | Start MCP server (stdio or SSE) |

---

## MCP Server

```bash
jetsam serve                    # stdio transport
jetsam serve --transport sse    # HTTP/SSE transport
```

### Tools

#### Workflow Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `status` | — | Repository state snapshot |
| `save` | `message?`, `include?`, `exclude?`, `files?` | Plan or commit result |
| `sync` | `strategy?` | Plan or sync result |
| `ship` | `message?`, `include?`, `exclude?`, `to?`, `open_pr?`, `merge?` | Plan |
| `pr_create` | `title?`, `body?`, `draft?`, `base?` | Plan or PR details |
| `pr_list` | `state?`, `author?` | PR list with status |
| `issues` | `state?`, `labels?`, `assignee?` | Issue list |
| `checks` | `pr?`, `branch?` | Check suite results |
| `switch` | `branch`, `create?` | Switch result |
| `start` | `issue?`, `name?`, `worktree?` | New branch/worktree |
| `finish` | `merge_strategy?`, `delete_branch?` | Plan |
| `log` | `count?`, `branch?` | Commit list |
| `diff` | `target?`, `stat_only?` | Diff content or stat summary |
| `release` | `tag`, `title?`, `notes?`, `draft?` | Plan |

#### Plan Management Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `update_plan` | `plan_id`, plus any parameter from the original verb | Updated plan with diff |
| `confirm` | `plan_id` | Execution results per step |
| `cancel_plan` | `plan_id` | Acknowledgment |
| `show_plan` | `plan_id` | Current plan state |

#### Pass-Through Tool

| Tool | Parameters | Returns |
|------|-----------|---------|
| `git` | `args` (string array) | Structured output from git command |

### Plan/Confirm Protocol

Workflow tools that mutate state (`ship`, `save`, `sync`, `finish`, `release`, `pr_create`) return plans by default in MCP mode. The agent reviews, optionally refines with `update_plan`, then calls `confirm`.

The protocol:

1. **Any workflow tool** → returns `{"plan_id": "...", "steps": [...], "warnings": [...]}`
2. **`update_plan(plan_id, ...)`** → patches the plan, returns updated plan with `"diff"` showing changes
3. **`confirm(plan_id)`** → executes, returns `{"results": [{"step": "...", "ok": true/false, ...}]}`
4. **Plans expire after 5 minutes.** Stale plans return an error suggesting the agent re-plan.
5. **Plans are invalidated if repo state changes.** The plan stores a state hash; confirm checks it.

For tools that only read (`status`, `log`, `diff`, `pr_list`, `issues`, `checks`), results are returned directly with no plan step.

---

## Platform Abstraction

Auto-detects the platform from the remote URL and delegates to the appropriate CLI:

| Operation | GitHub (`gh`) | GitLab (`glab`) |
|-----------|--------------|-----------------|
| Create PR/MR | `gh pr create` | `glab mr create` |
| List PRs/MRs | `gh pr list` | `glab mr list` |
| Check CI | `gh pr checks` | `glab ci status` |
| Create release | `gh release create` | `glab release create` |
| Issues | `gh issue list` | `glab issue list` |

Users and agents never think about which platform they're on. The verbs are the same. The tool translates.

---

## Smart Defaults

The tool minimizes required arguments by inferring from context:

| Situation | Inference |
|-----------|-----------|
| `save` with no message | Generate from diff summary (short heuristic, optional LLM) |
| `save` with no file selection | Stage all modified tracked files (not untracked) |
| `pr` with no title | Use branch name or first commit message |
| `ship` with open PR | Skip PR creation, update existing |
| `ship` with failing checks | Warn and stop (override with `--force`) |
| `ship` default scope | Stage → commit → push → PR open/update. `--merge` to go further. |
| `sync` on default branch | Pull only (no rebase) |
| `sync` on feature branch | Fetch + rebase onto default branch |
| `switch` with dirty working tree | Auto-stash, switch, pop |
| `start 42` | Create branch `issue-42-<title-slug>`, link to issue |
| `start` in worktree-initialized repo | Create worktree instead of branch |
| `finish` in worktree | Clean up worktree + branch, switch to main worktree |

---

## Worktree Integration

When the repo is initialized for worktrees (via `git-wt init` or detected automatically), the tool adapts its behavior:

| Verb | Without Worktrees | With Worktrees |
|------|------------------|----------------|
| `start` | `git checkout -b` | `git worktree add` into trees directory |
| `switch` | `git stash` + `git checkout` + `git stash pop` | `cd` to worktree (or `git-wt resume`) |
| `finish` | Delete branch | Remove worktree + delete branch |
| `status` | Branch info | Branch info + worktree path + other active worktrees |
| `tidy` | Prune merged branches | Prune worktrees + branches |

Shared paths (`.lq/` for blq, caches, databases) are symlinked automatically when creating worktrees, following the `.git-worktree-shared` convention from git-wt.

This is a **Phase 3+** feature. The tool works without worktrees. When worktree support is detected, it enhances the existing verbs rather than adding new ones.

---

## Error Handling

Errors are clear, actionable, and structured.

### Human mode

```
$ jetsam ship -m "fix"

  ✗ Cannot ship: branch is 2 commits behind main

  Fix: jetsam sync     (rebase onto main)
  Then: jetsam ship -m "fix"
```

### Agent mode (JSON)

```json
{
  "error": "branch_behind",
  "message": "Branch is 2 commits behind main",
  "suggested_action": "sync",
  "recoverable": true
}
```

### Plan execution failures

When a plan step fails mid-execution, the result includes what completed and what didn't:

```json
{
  "plan_id": "p_7f3a",
  "status": "partial",
  "results": [
    {"step": "stage", "ok": true, "files": 3},
    {"step": "commit", "ok": true, "sha": "abc1234"},
    {"step": "push", "ok": false, "error": "rejected_non_fast_forward",
     "message": "Remote has changes. Run sync first.",
     "recoverable": true}
  ],
  "completed_steps": 2,
  "total_steps": 4,
  "rollback_hint": "Commit abc1234 is local-only. Safe to amend or reset."
}
```

---

## Configuration

```yaml
# .jetsam/config.yaml (per-repo) or ~/.config/jetsam/config.yaml (global)
platform: auto            # auto | github | gitlab
merge_strategy: squash    # squash | merge | rebase
auto_push: false          # push after every save
ship_default: pr          # pr (stop at PR) | merge (go all the way)
pr_draft: false           # create PRs as draft by default
branch_prefix: ""         # e.g., "teague/" for namespaced branches
delete_on_merge: true     # delete branch after merge
worktree: auto            # auto (detect) | always | never
commit_message: heuristic # heuristic | prompt | llm
```

---

## Architecture

```
jetsam/
├── cli/
│   ├── main.py           # Click entrypoint, verb routing, pass-through dispatch
│   ├── verbs/            # One module per workflow verb
│   └── passthrough.py    # Delegates unknown verbs to git/gh/glab
├── mcp/
│   ├── server.py         # MCP server (stdio + SSE)
│   └── tools.py          # Tool definitions mapping to core
├── core/
│   ├── state.py          # Repository state snapshot builder
│   ├── planner.py        # Plan generation from state + intent
│   ├── plans.py          # Plan storage, update, validation, TTL
│   ├── executor.py       # Plan execution with step-by-step results
│   └── output.py         # Formatters (human, JSON, CSV, markdown)
├── platforms/
│   ├── base.py           # Abstract platform interface
│   ├── github.py         # gh CLI wrapper
│   └── gitlab.py         # glab CLI wrapper
├── git/
│   ├── wrapper.py        # git CLI wrapper with structured parsing
│   └── parsers.py        # Output parsers for common git commands
├── worktree/
│   └── integration.py    # Worktree detection, creation, shared paths
└── config/
    └── manager.py        # Config loading, defaults, platform detection
```

### Dependencies

- **Python 3.10+**
- **Click** — CLI framework
- **git** — must be installed and on PATH
- **gh** (optional) — required for GitHub platform operations
- **glab** (optional) — required for GitLab platform operations

No DuckDB dependency. No heavy frameworks. Thin wrappers that shell out and parse.

### MCP Server

The MCP server reuses the same `core/` and `platforms/` layers as the CLI. Both interfaces call `planner.py` and `executor.py`. The server is a thin adapter using the `mcp` Python SDK.

---

## Aliases

The long name is the package/brand. `jt` is the daily driver alias:

```bash
# In .bashrc / .zshrc (installed by `jetsam init --aliases`)
alias jt='jetsam'
alias jts='jetsam status'
alias jtv='jetsam save'
alias jty='jetsam sync'
alias jth='jetsam ship'
alias jtp='jetsam ship --pr'
alias jtw='jetsam switch'
alias jtl='jetsam log'
alias jtd='jetsam diff'
```

The `jt` prefix avoids collisions with common commands. All aliases are optional — `jetsam` always works as the full command.

---

## Relationship to Other Tools

| Tool | Role | Relationship |
|------|------|-------------|
| **Fledgling** | Code navigation for agents (MCP) | Complementary — Fledgling reads code, this tool operates on repos |
| **blq** | Build log capture and analysis | Complementary — blq analyzes test results, this tool ships the fix |
| **git-wt** | Worktree workflow (bash) | Subsumed — worktree operations integrate as a mode of this tool |
| **duck_hunt** | DuckDB extension for parsing logs | No dependency — different layer |
| **lazygit** | Interactive git TUI | Different audience — lazygit is visual, this tool is programmatic |
| **Graphite** | Stacked PR workflow | Different opinion — this tool doesn't impose a PR model |
| **GitKraken MCP** | Commercial IDE git integration | Overlapping scope but this is open source, CLI-first, platform-agnostic |
| **GitHub MCP Server** | Official GitHub MCP | Lower-level — exposes raw API; this tool composes workflows on top |

The intended workflow: an agent uses **Fledgling** to understand the code, makes changes, uses **this tool** to ship them, and uses **blq** to verify the build passed. Three MCP servers, three responsibilities.

---

## Non-Goals (v1)

- **Bitbucket/Azure DevOps support** — GitHub and GitLab only initially
- **Interactive TUI** — lazygit already does this well; this tool is verbs, not a dashboard
- **Merge conflict resolution** — surface the conflict, don't try to resolve it
- **Git hosting** — this is a client, not a platform
- **Rewriting history** — no interactive rebase; pass through to `git` directly
- **Full worktree management** — detect and integrate, don't replace git-wt entirely in v1

---

## Open Questions

1. ~~**Name**~~: **Resolved — jetsam.** Cargo deliberately thrown overboard to save a sinking ship. Maritime terminology maps to git concepts: jetsam (ship/push), flotsam (merge conflict debris), lagan (stash — sunk but marked for recovery), derelict (dead branches), dunnage (boilerplate). CLI alias: `jt`.

2. **Commit message generation**: Should `save` with no message generate one from the diff? Leaning toward: simple heuristic by default (file names + change summary), optional LLM integration via config. The heuristic should be good enough that agents don't waste tokens writing commit messages.

3. **`ship` default scope**: Current spec says default stops at push + PR open/update, `--merge` goes further. This feels right for team workflows. Solo projects might want merge as default — make it configurable via `ship_default` in config.

4. **Plan state hash**: Plans store a hash of the repo state at creation time. If the state changes between plan and confirm, the plan is invalidated. Question: how aggressive should this be? Any change (even unrelated files) invalidates? Or only changes to files in the plan? Leaning toward: only changes that affect the plan (staged files, target branch HEAD).

5. **Auth**: Delegates entirely to `gh`/`glab`. If those aren't authenticated, the tool tells you to run `gh auth login` or `glab auth login`. No token management in this tool.

6. **Offline mode**: Pure-git operations (save, log, diff, switch, pass-through) work without network. Platform operations (pr, issues, checks, ship with PR) gracefully degrade with clear errors.

7. **git-wt absorption**: Should this tool eventually replace git-wt entirely, or should git-wt remain standalone with this tool detecting and integrating? Leaning toward: git-wt stays standalone (it's bash, zero deps, fast), this tool detects it and adds workflow verbs on top.

---

## Success Metrics

- Agent token usage for git operations reduced by 60%+ vs raw `git`/`gh` calls
- A `ship` replaces 4-6 individual commands
- Plans reduce agent error recovery loops (retry after push rejection, etc.) by 80%
- Zero-config setup: `init` in any GitHub/GitLab repo and go
- Time from `init` to first `ship`: under 60 seconds
- Pass-through means zero learning curve — anything you can do with git, you can do here

---

## Implementation Priority

### Phase 1: Core (week 1-2)
- `status` (state snapshot)
- `save` (stage + commit with include/exclude)
- `sync` (pull/rebase/push)
- `log`, `diff` (query verbs)
- Pass-through to `git` with structured output
- GitHub platform only
- JSON output mode
- Basic MCP server (status, save, sync, log, git pass-through)
- Plan/confirm for `save` and `sync`

### Phase 2: Ship (week 3-4)
- `ship` (full pipeline with mutable plans)
- `pr` (create/update)
- `checks`
- `switch` (stash-aware)
- `update_plan` / `confirm` / `cancel_plan` MCP tools
- Config system
- `init` with platform detection

### Phase 3: Workflow (week 5-6)
- `start` / `finish` (issue-linked lifecycle)
- `tidy` (cleanup)
- `issues`, `prs` (query tools)
- GitLab support
- Worktree detection and integration
- Shell completions

### Phase 4: Polish (week 7-8)
- `release`
- Alias system
- Error recovery suggestions
- Worktree shared paths
- Documentation and examples
- Package and publish (PyPI)
