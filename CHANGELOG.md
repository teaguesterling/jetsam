# Changelog

## Unreleased

### Security
- **Merge `strategy` / review `event` allowlisted on the MCP path.** Both were interpolated into a `gh` argv as `--<value>`; the CLI constrained them via `click.Choice` but the MCP path did not, so `strategy="admin"` produced `gh pr merge --admin` (branch-protection bypass). Both now validate against canonical sets (`platforms.base.MERGE_STRATEGIES` / `REVIEW_EVENTS`) that the CLI also references, at plan-build time and again at the platform boundary. (GHSA-w893-5jfc-rwq9, #19)
- **Follow-up allowlist audit: every fixed-value-set MCP param is validated before subprocess argv.** `pr_list`/`issues` `state` filters, `issue_close` `reason`, and the sync `strategy` (previously an out-of-set sync strategy silently coerced to "merge") are now rejected with the standard `{error, message, recoverable}` dict on the MCP path and `ValueError` at the platform layer (GitHub and GitLab adapters). Free-form params (titles, bodies, messages, branch names) are deliberately not restricted. (#19)

### Bug fixes
- **`save`/`ship` commit exactly the plan's file list.** `_exec_commit` ran `git commit -m` with no pathspec, committing the whole index — an unrelated already-staged file (or one removed via `modify_plan(exclude=…)`, which only filtered the stage step) still landed in the commit. The commit step now carries the plan's explicit pathspec (`git commit -m <msg> -- <files>`); plans without a file list keep the bare-commit behavior. `modify_plan(exclude=…)` filters the commit pathspec too. (#19)
- **`issue_close(reason="not-planned")` works now.** The documented hyphenated spelling was passed to gh verbatim, which rejects it; it is normalized to the `"not planned"` form gh accepts.
- **Platform API-response models tolerate unknown fields** instead of crashing on `unexpected keyword argument` when gh/glab JSON grows a field or adapter/model modules skew across an editable-install upgrade. (#24)

### Changed
- **Removed the dead `auto_confirm_safe_verbs` runtime-config knob.** It was settable, validated, and documented but consumed nowhere. Wiring it up would have added an auto-confirm bypass of the plan→confirm gate, so it was removed rather than activated. (#19)
- **Truthful stash warnings on `switch`/`start`.** Both warned "Dirty changes will be stashed" even when the only dirt was untracked files — which `git stash push` (as jetsam invokes it, without `-u`) does not capture. Untracked-only trees now plan no stash steps and get an informational "untracked files are not stashed; they stay in place" note; trees with tracked dirt get a warning that says *tracked* changes are stashed. (#19)

## v1.1.6

### Bug fixes
- **`jetsam --version` reports the real version.** `__version__` was a hardcoded string (`1.1.2`, stale since v1.1.3) that misreported the release. It's now derived from the installed package metadata (`importlib.metadata`), single-sourced from `pyproject.toml`, so it can't drift from the release again.

## v1.1.5

### Bug fixes
- **`finish` actually merges the PR now.** `build_state()` never populates `state.pr` (the lookup costs a platform round-trip), so `plan_finish`'s `if state.pr:` never fired — from both the MCP tool and the CLI verb, `finish` silently planned only `checkout + fetch + branch_delete` and left the PR open, while reading as if it had shipped. Both entry points now call the new `attach_open_pr()` (open PRs only — `pr_for_branch` also returns merged/closed ones, which must never be re-merged), and `plan_finish` warns explicitly when there is no open PR instead of silently degrading to local cleanup.
- **`ssh://` remotes are recognized.** `parse_remote_url` only matched scp-style (`git@host:path`) and `https://` URLs, so a repo cloned with the explicit `ssh://git@github.com/owner/repo.git` spelling got platform "unknown" and every platform op failed with "No platform configured" — jetsam's own origin uses this form. Now matched (including optional user@ and :port).
- **`ship` pushes fresh branches.** The push step was gated on `has_something_to_commit or ahead > 0`, but a branch with no upstream always reports `ahead=0` — so `ship(files=[])` on a just-created branch planned `pr_create` against a branch the remote had never seen. No upstream now implies a push (with `set_upstream`).
- **`mergeable` is real data now.** The GitHub adapter never requested the `mergeable` field from `gh`, so `pr_view`/`pr_list`/`pr_for_branch` reported `mergeable: false` for every PR regardless of actual state. The field is now requested and mapped; a new `mergeable_state` ("mergeable" / "conflicting" / "unknown") preserves gh's tri-state so callers can tell a real conflict from GitHub still computing.
- **`plan_not_found` on immediate confirm — plan store is no longer repo/cwd-pinned.** The MCP plan store was a process-global singleton pinned to whichever repo the server first touched (and `PlanStore("")` rooted at the process cwd), so a plan saved for one repo could be invisible to `confirm` seconds later. Plans now live in a stable per-user dir (`~/.local/state/jetsam/plans/`, XDG-aware) keyed by `plan_id`; `confirm` still executes in the plan's own repo. Also validates plan ids (`^p_[0-9a-f]+$`) and reports the searched dir on `plan_not_found`. Closes #17 (and the #19 id-validation item).

## v1.1.4

### Bug fixes
- **`save`/`ship` no longer collapse `files=[]` into `files=None`.** `_resolve_files` gated on `if files:`, so an explicit empty list ("stage nothing") fell through to auto-detect and swept all modified tracked files. Now `files is not None` is honored: `ship(files=[])` on an already-committed branch yields exactly `[push, pr_create]` — no spurious commit.

### Features
- **`noise_paths` config** — auto-stage (`files=None`) never sweeps these globs/dirs (default: `.jetsam`, `.kibitzer`, `.bird`, `.riggs`, `*.sqlite*`), so agent/tool runtime churn stays out of commits. Naming a path explicitly via `files=` still stages it.

## v1.1.3

### Bug fixes
- **Fix `stale_plan` on cross-repo `confirm()`** in multi-repo sessions. A plan from `save`/`sync`/etc. recorded its `state_hash` for the repo at `cwd`, but `confirm()` re-validated and executed against the MCP server's default `active_root` — so any session touching more than one repo failed `stale_plan` on every cross-repo `confirm()`. Plans now persist their `repo_root`, and `confirm` validates and executes in the plan's own repo. (Sequel to the v1.1.1 `.jetsam/` hash fix — same lineage, different cause.)

## v1.1.1

### Bug fixes
- **Fix `stale_plan` on every `confirm()` for `sync`/`release`/`tidy`** (#12). jetsam's own `.jetsam/` plan-storage directory is untracked, and the unscoped state hash counted untracked files — so writing a plan invalidated it before it could be confirmed. `build_state` now excludes jetsam's own `.jetsam/` paths from the snapshot, so the repo state and its hash never depend on jetsam's internals.
- `release` and `tidy` plans now set `exclude_remote_tracking=True` like `sync`/`finish`, so a background `git fetch` shifting ahead/behind between plan and confirm no longer triggers `stale_plan`.

## v1.1.0

### New features
- `jetsam config` verb — view, get, and set configuration from the CLI (P7-003)
- `jetsam ship --draft` flag — create draft PRs from the command line (P7-001)

### Quality improvements
- Fix SHA extraction in executor — uses `git rev-parse` instead of fragile output parsing (P5-001)
- Consolidate `PlatformError` into `platforms/base.py` — single import for all adapters (P5-002)
- Add `py.typed` marker for PEP 561 type checking support (P5-003)
- Add test coverage measurement with `pytest-cov` — 63% baseline (P5-004)
- Trigger expired plan cleanup on MCP server start (P5-005)

## v1.0.0

### API stability
- All MCP tool error responses standardized to `{error, message, recoverable}` format (P6-002)
- `Plan.to_dict()` includes `params`, `scope`, and `state_hash` (P6-003)
- 9 configuration options wired into planners (P6-001): `auto_push`, `pr_draft`,
  `ship_default`, `merge_strategy`, `branch_prefix`, `delete_on_merge`, `worktree`
- 363 tests, 0 mypy strict errors, 0 lint errors

### Platform support
- GitHub: fully supported via `gh` CLI
- GitLab: core operations supported via `glab` CLI; PR comment/review/close
  operations raise `NotImplementedError` (planned for v1.1.0)

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
