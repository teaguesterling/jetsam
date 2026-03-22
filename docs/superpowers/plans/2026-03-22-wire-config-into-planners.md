# Wire Config into Planners — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `JetsamConfig` into planner functions so config options control plan generation defaults.

**Architecture:** Each planner accepts an optional `config: JetsamConfig | None` parameter. Entry points (CLI verbs, MCP tools) load config once and pass it through. Parameters that overlap with config use `None` defaults so the planner can distinguish "caller set this" from "caller used the default." Precedence: explicit param > config > hardcoded default.

**Tech Stack:** Python 3.12, dataclasses, click (CLI), FastMCP (MCP tools), pytest

**Spec:** `docs/superpowers/specs/2026-03-22-wire-config-into-planners-design.md`

---

## File Structure

| File | Responsibility | Change Type |
|---|---|---|
| `src/jetsam/core/planner.py` | Plan generation from state + intent | Modify: add `config` param to 4 planners, add `draft` to `plan_ship`, change sentinel defaults |
| `src/jetsam/mcp/tools.py` | MCP tool definitions | Modify: load config in 4 tools, pass to planners, change sentinel defaults |
| `src/jetsam/cli/verbs/save.py` | CLI save command | Modify: load config, pass to planner |
| `src/jetsam/cli/verbs/ship.py` | CLI ship command | Modify: load config, pass to planner |
| `src/jetsam/cli/verbs/start.py` | CLI start command | Modify: load config, pass to planner |
| `src/jetsam/cli/verbs/finish.py` | CLI finish command | Modify: load config, pass to planner, change `--strategy` default |
| `tests/test_planner.py` | Planner tests | Modify: add ~17 config-related tests |

---

### Task 1: Wire config into `plan_save` (auto_push)

**Files:**
- Modify: `src/jetsam/core/planner.py:49-100`
- Test: `tests/test_planner.py`

- [ ] **Step 1: Write failing tests for plan_save config**

Add to `tests/test_planner.py`. First, add these top-level imports (alongside the existing imports at line 1-4):

```python
from jetsam.config.manager import JetsamConfig
from jetsam.core.planner import plan_start
```

Then add these tests inside `class TestPlanSave`:

    def test_auto_push_adds_push_step(self):
        state = _make_state()
        config = JetsamConfig(auto_push=True)
        plan = plan_save(state, plan_id="p_test", message="fix bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "push" in actions
        push_step = next(s for s in plan.steps if s.action == "push")
        assert push_step.params["branch"] == "feature"

    def test_auto_push_false_no_push_step(self):
        state = _make_state()
        config = JetsamConfig(auto_push=False)
        plan = plan_save(state, plan_id="p_test", message="fix bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "push" not in actions

    def test_auto_push_on_default_branch_no_push(self):
        state = _make_state(branch="main", default_branch="main")
        config = JetsamConfig(auto_push=True)
        plan = plan_save(state, plan_id="p_test", message="fix bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "push" not in actions

    def test_default_config_no_push(self):
        """Default config (auto_push=False) preserves existing behavior."""
        state = _make_state()
        config = JetsamConfig()
        plan = plan_save(state, plan_id="p_test", message="fix bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "push" not in actions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py::TestPlanSave::test_auto_push_adds_push_step -v`
Expected: FAIL — `plan_save() got an unexpected keyword argument 'config'`

- [ ] **Step 3: Implement config in plan_save**

In `src/jetsam/core/planner.py`, add the import at the top (after existing imports):

```python
from jetsam.config.manager import JetsamConfig, load_config
```

Change `plan_save` signature and body. The full updated function:

```python
def plan_save(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
    config: JetsamConfig | None = None,
) -> Plan:
    """Generate a plan for the 'save' verb (stage + commit)."""
    if config is None:
        config = load_config(state.repo_root)

    # Determine which files to stage
    target_files = _resolve_files(state, include, exclude, files)
    warnings: list[str] = []

    if not target_files and not state.staged:
        warnings.append("No files to stage or commit")
        return Plan(
            plan_id=plan_id,
            verb="save",
            steps=[],
            state_hash=state.compute_hash(),
            warnings=warnings,
            params={"message": message, "include": include, "exclude": exclude, "files": files},
        )

    # Determine commit message
    if not message:
        message = _generate_message_heuristic(target_files)

    steps: list[PlanStep] = []

    if target_files:
        steps.append(PlanStep(action="stage", params={"files": target_files}))

    all_staged = list(set(state.staged + target_files))
    steps.append(
        PlanStep(
            action="commit",
            params={"message": message, "file_count": len(all_staged)},
        )
    )

    # Auto-push if configured (but not on default branch)
    if config.auto_push and state.branch != state.default_branch:
        steps.append(
            PlanStep(
                action="push",
                params={
                    "branch": state.branch,
                    "remote": "origin",
                    "set_upstream": state.upstream is None,
                },
            )
        )

    scope = target_files or state.staged

    return Plan(
        plan_id=plan_id,
        verb="save",
        steps=steps,
        state_hash=state.compute_hash(scope=scope),
        scope=scope,
        warnings=warnings,
        params={"message": message, "include": include, "exclude": exclude, "files": files},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py::TestPlanSave -v`
Expected: All PASS (including existing tests — default config matches current behavior)

- [ ] **Step 5: Commit**

```bash
git add src/jetsam/core/planner.py tests/test_planner.py
git commit -m "feat: wire config into plan_save (auto_push)"
```

---

### Task 2: Wire config into `plan_ship` (pr_draft, ship_default, merge_strategy)

**Files:**
- Modify: `src/jetsam/core/planner.py:197-304`
- Test: `tests/test_planner.py`

- [ ] **Step 1: Write failing tests for plan_ship config**

Add to `tests/test_planner.py`:

```python
# Inside class TestPlanShip:

    def test_pr_draft_adds_draft_to_pr_create(self):
        state = _make_state()
        config = JetsamConfig(pr_draft=True)
        plan = plan_ship(state, plan_id="p_test", message="ship", config=config)
        pr_step = next(s for s in plan.steps if s.action == "pr_create")
        assert pr_step.params["draft"] is True

    def test_pr_draft_false_sets_draft_false(self):
        state = _make_state()
        config = JetsamConfig(pr_draft=False)
        plan = plan_ship(state, plan_id="p_test", message="ship", config=config)
        pr_step = next(s for s in plan.steps if s.action == "pr_create")
        assert pr_step.params["draft"] is False

    def test_explicit_draft_overrides_config(self):
        state = _make_state()
        config = JetsamConfig(pr_draft=True)
        plan = plan_ship(state, plan_id="p_test", message="ship", draft=False, config=config)
        pr_step = next(s for s in plan.steps if s.action == "pr_create")
        assert pr_step.params["draft"] is False

    def test_ship_default_merge(self):
        state = _make_state()
        config = JetsamConfig(ship_default="merge")
        plan = plan_ship(state, plan_id="p_test", message="ship", config=config)
        actions = [s.action for s in plan.steps]
        assert "pr_create" in actions
        assert "pr_merge" in actions

    def test_ship_default_pr(self):
        state = _make_state()
        config = JetsamConfig(ship_default="pr")
        plan = plan_ship(state, plan_id="p_test", message="ship", config=config)
        actions = [s.action for s in plan.steps]
        assert "pr_create" in actions
        assert "pr_merge" not in actions

    def test_explicit_merge_overrides_ship_default(self):
        state = _make_state()
        config = JetsamConfig(ship_default="pr")
        plan = plan_ship(state, plan_id="p_test", message="ship", merge=True, config=config)
        actions = [s.action for s in plan.steps]
        assert "pr_merge" in actions

    def test_explicit_no_pr_overrides_ship_default(self):
        state = _make_state()
        config = JetsamConfig(ship_default="pr")
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=False, config=config)
        actions = [s.action for s in plan.steps]
        assert "pr_create" not in actions

    def test_merge_strategy_in_pr_merge_step(self):
        state = _make_state()
        config = JetsamConfig(merge_strategy="rebase")
        plan = plan_ship(state, plan_id="p_test", message="ship", merge=True, config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["strategy"] == "rebase"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py::TestPlanShip::test_pr_draft_adds_draft_to_pr_create -v`
Expected: FAIL — `plan_ship() got an unexpected keyword argument 'config'`

- [ ] **Step 3: Implement config in plan_ship**

Change `plan_ship` signature and body in `src/jetsam/core/planner.py`:

```python
def plan_ship(
    state: RepoState,
    plan_id: str,
    message: str | None = None,
    include: str | None = None,
    exclude: str | None = None,
    files: list[str] | None = None,
    to: str | None = None,
    open_pr: bool | None = None,
    merge: bool | None = None,
    draft: bool | None = None,
    config: JetsamConfig | None = None,
) -> Plan:
    """Generate a plan for the 'ship' verb (stage + commit + push + PR)."""
    if config is None:
        config = load_config(state.repo_root)

    # Resolve defaults from config when not explicitly set
    if open_pr is None and merge is None:
        if config.ship_default == "merge":
            open_pr = True
            merge = True
        else:
            open_pr = True
            merge = False
    else:
        if open_pr is None:
            open_pr = True
        if merge is None:
            merge = False

    if draft is None:
        draft = config.pr_draft

    steps: list[PlanStep] = []
    warnings: list[str] = []
    target_branch = to or state.default_branch

    # Stage files
    target_files = _resolve_files(state, include, exclude, files)
    if target_files:
        steps.append(PlanStep(action="stage", params={"files": target_files}))

    # Commit — only if there's something to commit
    has_something_to_commit = bool(target_files or state.staged)
    if has_something_to_commit:
        all_staged = list(set(state.staged + target_files))
        if not message:
            message = _generate_message_heuristic(all_staged)
        steps.append(
            PlanStep(
                action="commit",
                params={"message": message, "file_count": len(all_staged)},
            )
        )
    elif not message:
        message = ""

    # Push — if there are commits to push or we just committed
    if has_something_to_commit or state.ahead > 0:
        steps.append(
            PlanStep(
                action="push",
                params={
                    "branch": state.branch,
                    "remote": "origin",
                    "set_upstream": state.upstream is None,
                },
            )
        )

    # PR
    if open_pr:
        if state.pr:
            steps.append(
                PlanStep(
                    action="pr_update",
                    params={"number": state.pr.number},
                )
            )
        else:
            steps.append(
                PlanStep(
                    action="pr_create",
                    params={
                        "title": message or state.branch,
                        "base": target_branch,
                        "draft": draft,
                    },
                )
            )

    # Merge
    if merge:
        if state.branch == target_branch:
            warnings.append("Cannot merge branch into itself")
        else:
            steps.append(
                PlanStep(
                    action="pr_merge",
                    params={
                        "base": target_branch,
                        "strategy": config.merge_strategy,
                    },
                )
            )

    if not steps:
        warnings.append("Nothing to commit or push")

    # Warnings
    if state.behind > 0:
        warnings.append(
            f"Branch is {state.behind} commits behind {state.upstream or state.default_branch}"
        )

    scope = target_files or state.staged
    return Plan(
        plan_id=plan_id,
        verb="ship",
        steps=steps,
        state_hash=state.compute_hash(scope=scope),
        scope=scope,
        warnings=warnings,
        params={
            "message": message,
            "include": include,
            "exclude": exclude,
            "files": files,
            "to": to,
            "open_pr": open_pr,
            "merge": merge,
            "draft": draft,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py::TestPlanShip -v`
Expected: All PASS (new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/jetsam/core/planner.py tests/test_planner.py
git commit -m "feat: wire config into plan_ship (pr_draft, ship_default, merge_strategy)"
```

---

### Task 3: Wire config into `plan_start` (branch_prefix, worktree)

**Files:**
- Modify: `src/jetsam/core/planner.py:337-407`
- Test: `tests/test_planner.py`

- [ ] **Step 1: Write failing tests for plan_start config**

Add a new test class to `tests/test_planner.py` (the `plan_start` and `JetsamConfig` imports were added in Task 1):

```python
class TestPlanStart:
    def test_config_branch_prefix(self):
        state = _make_state()
        config = JetsamConfig(branch_prefix="feature/")
        plan = plan_start(state, plan_id="p_test", target="fix-bug", config=config)
        assert plan.params["branch"] == "feature/fix-bug"

    def test_explicit_prefix_overrides_config(self):
        state = _make_state()
        config = JetsamConfig(branch_prefix="feature/")
        plan = plan_start(
            state, plan_id="p_test", target="fix-bug",
            branch_prefix="hotfix/", config=config,
        )
        assert plan.params["branch"] == "hotfix/fix-bug"

    def test_empty_prefix_config_no_prefix(self):
        state = _make_state()
        config = JetsamConfig(branch_prefix="")
        plan = plan_start(state, plan_id="p_test", target="fix-bug", config=config)
        assert plan.params["branch"] == "fix-bug"

    def test_worktree_always_uses_worktree(self):
        state = _make_state(dirty=False)
        config = JetsamConfig(worktree="always")
        plan = plan_start(state, plan_id="p_test", target="fix-bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "worktree_add" in actions
        assert "checkout" not in actions

    def test_worktree_never_uses_checkout(self):
        state = _make_state(dirty=False)
        config = JetsamConfig(worktree="never")
        plan = plan_start(state, plan_id="p_test", target="fix-bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "checkout" in actions
        assert "worktree_add" not in actions

    def test_worktree_auto_defaults_to_checkout(self):
        state = _make_state(dirty=False)
        config = JetsamConfig(worktree="auto")
        plan = plan_start(state, plan_id="p_test", target="fix-bug", config=config)
        actions = [s.action for s in plan.steps]
        assert "checkout" in actions

    def test_explicit_worktree_true_overrides_config_never(self):
        state = _make_state(dirty=False)
        config = JetsamConfig(worktree="never")
        plan = plan_start(
            state, plan_id="p_test", target="fix-bug",
            worktree=True, config=config,
        )
        actions = [s.action for s in plan.steps]
        assert "worktree_add" in actions

    def test_explicit_worktree_false_overrides_config_always(self):
        state = _make_state(dirty=False)
        config = JetsamConfig(worktree="always")
        plan = plan_start(
            state, plan_id="p_test", target="fix-bug",
            worktree=False, config=config,
        )
        actions = [s.action for s in plan.steps]
        assert "checkout" in actions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py::TestPlanStart::test_config_branch_prefix -v`
Expected: FAIL — `plan_start() got an unexpected keyword argument 'config'`

- [ ] **Step 3: Implement config in plan_start**

Change `plan_start` in `src/jetsam/core/planner.py`:

```python
def plan_start(
    state: RepoState,
    plan_id: str,
    target: str,
    issue_title: str | None = None,
    branch_prefix: str | None = None,
    worktree: bool | None = None,
    base: str | None = None,
    config: JetsamConfig | None = None,
) -> Plan:
    """Generate a plan for the 'start' verb (begin work on issue/feature).

    Args:
        target: Issue number (e.g. "42") or branch name (e.g. "fix-parser").
        issue_title: Title of the issue (for slug generation if target is numeric).
        branch_prefix: Optional prefix for branch names (e.g. "feature/").
            None means use config default; "" means no prefix.
        worktree: If True, create a worktree instead of switching branches.
            None means use config default.
        base: Base branch to create from (default: default_branch).
    """
    if config is None:
        config = load_config(state.repo_root)

    # Resolve branch_prefix: explicit (including "") > config
    if branch_prefix is None:
        branch_prefix = config.branch_prefix

    # Resolve worktree: explicit bool > config
    if worktree is None:
        worktree = config.worktree == "always"

    steps: list[PlanStep] = []
    warnings: list[str] = []
    actual_base = base or state.default_branch

    # Determine branch name
    if target.isdigit():
        issue_num = int(target)
        if issue_title:
            slug = _slugify(issue_title)
            branch_name = f"{issue_num}-{slug}"
        else:
            branch_name = f"issue-{issue_num}"
    else:
        branch_name = target

    # Apply branch prefix
    if branch_prefix and not branch_name.startswith(branch_prefix):
        branch_name = f"{branch_prefix}{branch_name}"

    if worktree:
        steps.append(PlanStep(
            action="worktree_add",
            params={"branch": branch_name, "base": actual_base},
        ))
    else:
        if state.dirty:
            warnings.append("Dirty changes will be stashed before switching")
            steps.append(PlanStep(
                action="stash",
                params={"message": f"jetsam start: stash before {branch_name}"},
            ))

        steps.append(PlanStep(
            action="checkout",
            params={"branch": branch_name, "create": True, "start_point": actual_base},
        ))

        if state.dirty:
            steps.append(PlanStep(action="stash_pop"))

    return Plan(
        plan_id=plan_id,
        verb="start",
        steps=steps,
        state_hash=state.compute_hash(),
        warnings=warnings,
        params={
            "target": target,
            "branch": branch_name,
            "base": actual_base,
            "worktree": worktree,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py::TestPlanStart -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/jetsam/core/planner.py tests/test_planner.py
git commit -m "feat: wire config into plan_start (branch_prefix, worktree)"
```

---

### Task 4: Wire config into `plan_finish` (merge_strategy, delete_on_merge)

**Files:**
- Modify: `src/jetsam/core/planner.py:410-488`
- Test: `tests/test_planner.py`

- [ ] **Step 1: Write failing tests for plan_finish config**

Add inside `class TestPlanFinish` in `tests/test_planner.py` (note: `PRInfo` is already imported by existing test `test_with_existing_pr`; if not yet at top level, add `from jetsam.core.state import PRInfo` to the top-level imports):

    def test_config_merge_strategy_rebase(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(merge_strategy="rebase")
        plan = plan_finish(state, plan_id="p_test", config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["strategy"] == "rebase"

    def test_config_merge_strategy_merge(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(merge_strategy="merge")
        plan = plan_finish(state, plan_id="p_test", config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["strategy"] == "merge"

    def test_explicit_strategy_overrides_config(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(merge_strategy="rebase")
        plan = plan_finish(state, plan_id="p_test", strategy="squash", config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["strategy"] == "squash"

    def test_delete_on_merge_false_skips_delete(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(delete_on_merge=False)
        plan = plan_finish(state, plan_id="p_test", config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["delete_branch"] is False

    def test_delete_on_merge_true_deletes(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(delete_on_merge=True)
        plan = plan_finish(state, plan_id="p_test", config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["delete_branch"] is True

    def test_explicit_no_delete_overrides_config(self):
        pr = PRInfo(number=42, state="open", title="feature")
        state = _make_state(pr=pr)
        config = JetsamConfig(delete_on_merge=True)
        plan = plan_finish(state, plan_id="p_test", no_delete=True, config=config)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["delete_branch"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py::TestPlanFinish::test_config_merge_strategy_rebase -v`
Expected: FAIL — `plan_finish() got an unexpected keyword argument 'config'`

- [ ] **Step 3: Implement config in plan_finish**

Change `plan_finish` in `src/jetsam/core/planner.py`:

```python
def plan_finish(
    state: RepoState,
    plan_id: str,
    strategy: str | None = None,
    no_delete: bool | None = None,
    worktree_path: str | None = None,
    config: JetsamConfig | None = None,
) -> Plan:
    """Generate a plan for the 'finish' verb (merge PR, clean up branch).

    Args:
        strategy: Merge strategy ("squash", "merge", "rebase"). None means use config.
        no_delete: Skip branch deletion. None means use config.delete_on_merge.
        worktree_path: If in a worktree, path to remove.
    """
    if config is None:
        config = load_config(state.repo_root)

    # Resolve defaults from config
    if strategy is None:
        strategy = config.merge_strategy
    if no_delete is None:
        no_delete = not config.delete_on_merge

    steps: list[PlanStep] = []
    warnings: list[str] = []

    if state.branch == state.default_branch:
        warnings.append("Already on default branch — nothing to finish")
        return Plan(
            plan_id=plan_id,
            verb="finish",
            steps=[],
            state_hash=state.compute_hash(exclude_remote_tracking=True),
            exclude_remote_tracking=True,
            warnings=warnings,
            params={"strategy": strategy, "no_delete": no_delete},
        )

    if state.dirty:
        warnings.append("Working tree has uncommitted changes")

    # Merge the PR if one exists
    if state.pr:
        steps.append(PlanStep(
            action="pr_merge",
            params={
                "number": state.pr.number,
                "strategy": strategy,
                "delete_branch": not no_delete,
            },
        ))

    # Switch back to default branch
    if worktree_path:
        steps.append(PlanStep(
            action="worktree_remove",
            params={"path": worktree_path},
        ))
    else:
        steps.append(PlanStep(
            action="checkout",
            params={"branch": state.default_branch},
        ))

    # Fetch to update refs after merge
    steps.append(PlanStep(action="fetch", params={"remote": "origin"}))

    # Delete branch locally (if not already deleted by merge)
    if not no_delete and not (state.pr and not worktree_path):
        # Only add explicit delete if pr_merge didn't handle it
        steps.append(PlanStep(
            action="branch_delete",
            params={"branch": state.branch},
        ))

    return Plan(
        plan_id=plan_id,
        verb="finish",
        steps=steps,
        state_hash=state.compute_hash(exclude_remote_tracking=True),
        exclude_remote_tracking=True,
        warnings=warnings,
        params={
            "branch": state.branch,
            "strategy": strategy,
            "no_delete": no_delete,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py::TestPlanFinish -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/jetsam/core/planner.py tests/test_planner.py
git commit -m "feat: wire config into plan_finish (merge_strategy, delete_on_merge)"
```

---

### Task 5: Wire config through MCP tools

**Files:**
- Modify: `src/jetsam/mcp/tools.py:61-82, 98-127, 257-289, 291-315`

- [ ] **Step 1: Add config import to tools.py**

At the top of `src/jetsam/mcp/tools.py`, add to imports:

```python
from jetsam.config.manager import load_config
```

- [ ] **Step 2: Update save() MCP tool**

In the `save()` tool function, add config loading and pass it:

```python
    @mcp.tool()
    def save(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Stage and commit changes. Returns a plan to confirm().

        Args:
            message: Commit message. Auto-generated if omitted.
            include: Glob pattern to filter files to stage.
            exclude: Glob pattern to filter files out.
            files: Explicit file paths to stage.
        """
        state = build_state()
        config = load_config(state.repo_root)
        pid = generate_plan_id()
        plan = plan_save(
            state, plan_id=pid,
            message=message, include=include, exclude=exclude, files=files,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()
```

- [ ] **Step 3: Update ship() MCP tool**

Change sentinel defaults and pass config:

```python
    @mcp.tool()
    def ship(
        message: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        files: list[str] | None = None,
        to: str | None = None,
        pr: bool | None = None,
        merge: bool | None = None,
        draft: bool | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: stage, commit, push, open PR. Returns a plan.

        Args:
            message: Commit message and PR title.
            include: Glob pattern to filter files to stage.
            exclude: Glob pattern to filter files out.
            files: Explicit file paths to stage.
            to: Target branch for PR (default: main/master).
            pr: Create/update a PR (default: uses config ship_default).
            merge: Also merge the PR after creating it.
            draft: Create PR as draft (default: uses config pr_draft).
        """
        state = build_state()
        config = load_config(state.repo_root)
        pid = generate_plan_id()
        plan = plan_ship(
            state, plan_id=pid,
            message=message, include=include, exclude=exclude,
            files=files, to=to, open_pr=pr, merge=merge, draft=draft,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()
```

- [ ] **Step 4: Update start() MCP tool**

Change sentinel defaults and pass config:

```python
    @mcp.tool()
    def start(
        target: str,
        worktree: bool | None = None,
        base: str | None = None,
        prefix: str | None = None,
    ) -> dict[str, Any]:
        """Start work on an issue or feature. Returns a plan to confirm().

        Args:
            target: Issue number (e.g. "42") or branch name (e.g. "fix-parser").
            worktree: Create a worktree instead of switching branches (default: uses config).
            base: Base branch (default: main/master).
            prefix: Branch name prefix (e.g. "feature/"). Default: uses config.
        """
        state = build_state()
        config = load_config(state.repo_root)
        pid = generate_plan_id()

        # Fetch issue title if target is numeric
        issue_title = None
        if target.isdigit():
            platform = _get_platform(state)
            if platform:
                issue = platform.issue_get(int(target))
                if issue:
                    issue_title = issue.title

        plan = plan_start(
            state, plan_id=pid,
            target=target, issue_title=issue_title,
            branch_prefix=prefix, worktree=worktree, base=base,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()
```

- [ ] **Step 5: Update finish() MCP tool**

Change sentinel defaults and pass config:

```python
    @mcp.tool()
    def finish(
        strategy: str | None = None,
        no_delete: bool | None = None,
    ) -> dict[str, Any]:
        """Merge PR and clean up branch. Returns a plan to confirm().

        Args:
            strategy: Merge strategy: "squash", "merge", or "rebase" (default: uses config).
            no_delete: Keep the branch after merging (default: uses config delete_on_merge).
        """
        state = build_state()
        config = load_config(state.repo_root)
        pid = generate_plan_id()

        worktree_path = None
        if state.worktree and state.worktree.active:
            worktree_path = state.worktree.current

        plan = plan_finish(
            state, plan_id=pid,
            strategy=strategy, no_delete=no_delete,
            worktree_path=worktree_path,
            config=config,
        )
        _get_store().save(plan)
        return plan.to_dict()
```

- [ ] **Step 6: Run all tests to verify nothing is broken**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/jetsam/mcp/tools.py
git commit -m "feat: wire config through MCP tools (save, ship, start, finish)"
```

---

### Task 6: Wire config through CLI verbs

**Known limitation:** Click `is_flag=True` options can only be present (True) or absent. When absent, we map to `None` to let config decide. This means CLI users can opt *into* features (e.g., `--merge`, `--worktree`, `--no-delete`) but cannot explicitly override config *back to default*. For example, a user with `ship_default="merge"` cannot do `jetsam ship` without merge unless they also pass `--no-pr`. Adding counterpart flags (`--no-merge`, `--delete`, `--no-worktree`) is deferred — the MCP layer supports full override.

**Files:**
- Modify: `src/jetsam/cli/verbs/save.py`
- Modify: `src/jetsam/cli/verbs/ship.py`
- Modify: `src/jetsam/cli/verbs/start.py`
- Modify: `src/jetsam/cli/verbs/finish.py`

- [ ] **Step 1: Update save.py**

Add import and wire config:

```python
from jetsam.config.manager import load_config
```

In the `save()` function body, after `state = build_state()`, add:

```python
    config = load_config(state.repo_root)
```

And update the `plan_save` call to pass `config=config`:

```python
    plan = plan_save(
        state,
        plan_id=plan_id,
        message=message,
        include=include,
        exclude=exclude,
        files=list(files) if files else None,
        config=config,
    )
```

- [ ] **Step 2: Update ship.py**

Add import:

```python
from jetsam.config.manager import load_config
```

In the `ship()` function body, after `state = build_state()`, add:

```python
    config = load_config(state.repo_root)
```

Change the `plan_ship` call. Note: `--no-pr` flag means when the user passes it, `no_pr=True` and we pass `open_pr=False`. When the user doesn't pass it, we want `open_pr=None` to let config decide. We need to change the flag handling:

Replace the `--no-pr` option:

```python
@click.option("--no-pr", "no_pr", is_flag=True, default=False, help="Skip PR creation")
```

And update the planner call:

```python
    plan = plan_ship(
        state,
        plan_id=plan_id,
        message=message,
        include=include,
        exclude=exclude,
        to=target,
        open_pr=False if no_pr else None,
        merge=merge or None,
        config=config,
    )
```

- [ ] **Step 3: Update start.py**

Add import:

```python
from jetsam.config.manager import load_config
```

In the `start()` function body, after `state = build_state()`:

```python
    config = load_config(state.repo_root)
```

Change the `--prefix` option default to `None`:

```python
@click.option("--prefix", default=None, help="Branch name prefix (e.g. feature/)")
```

Change the `--worktree` flag to pass `None` when not set. Since click `is_flag=True` gives `True` when passed and `False` when not, we need to convert:

Update the planner call:

```python
    plan = plan_start(
        state,
        plan_id=plan_id,
        target=target,
        issue_title=issue_title,
        branch_prefix=prefix,
        worktree=worktree or None,
        base=base,
        config=config,
    )
```

And update the type annotation for `prefix` in the function signature:

```python
    prefix: str | None,
```

- [ ] **Step 4: Update finish.py**

Add import:

```python
from jetsam.config.manager import load_config
```

Change `--strategy` default to `None`:

```python
@click.option("--strategy", type=click.Choice(["squash", "merge", "rebase"]),
              default=None, help="Merge strategy (default: from config, or squash)")
```

Change `--no-delete` to pass `None` when not set:

In the `finish()` function body, after `state = build_state()`:

```python
    config = load_config(state.repo_root)
```

Update the planner call:

```python
    plan = plan_finish(
        state,
        plan_id=plan_id,
        strategy=strategy,
        no_delete=no_delete or None,
        worktree_path=worktree_path,
        config=config,
    )
```

And update the type annotations:

```python
    strategy: str | None,
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/jetsam/cli/verbs/save.py src/jetsam/cli/verbs/ship.py src/jetsam/cli/verbs/start.py src/jetsam/cli/verbs/finish.py
git commit -m "feat: wire config through CLI verbs (save, ship, start, finish)"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass, including all ~17 new config tests

- [ ] **Step 2: Verify no import cycles**

Run: `python -c "from jetsam.core.planner import plan_save, plan_ship, plan_start, plan_finish"`
Expected: No errors

- [ ] **Step 3: Verify MCP tools import cleanly**

Run: `python -c "from jetsam.mcp.tools import register_tools"`
Expected: No errors

- [ ] **Step 4: Commit if any fixups needed, otherwise done**
