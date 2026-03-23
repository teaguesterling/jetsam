"""Tests for plan generation."""

from jetsam.config.manager import JetsamConfig
from jetsam.core.planner import plan_finish, plan_save, plan_ship, plan_start, plan_sync
from jetsam.core.state import RepoState


def _make_state(**kwargs):
    defaults = dict(
        branch="feature",
        upstream="origin/feature",
        default_branch="main",
        dirty=True,
        staged=["already_staged.py"],
        unstaged=["modified.py", "other.py"],
        untracked=["scratch.txt"],
        ahead=1,
        behind=0,
        stash_count=0,
        platform="github",
        remote="user/repo",
        remote_url="git@github.com:user/repo.git",
        head_sha="abc123",
        repo_root="/tmp/repo",
    )
    defaults.update(kwargs)
    return RepoState(**defaults)


class TestPlanSave:
    def test_basic(self):
        state = _make_state()
        plan = plan_save(state, plan_id="p_test", message="fix bug", config=JetsamConfig())
        assert plan.verb == "save"
        assert len(plan.steps) == 2  # stage + commit
        assert plan.steps[0].action == "stage"
        assert plan.steps[1].action == "commit"
        assert plan.steps[1].params["message"] == "fix bug"

    def test_include_pattern(self):
        state = _make_state(unstaged=["src/main.py", "tests/test_main.py", "docs/readme.md"])
        plan = plan_save(state, plan_id="p_test", message="fix", include="src/*.py", config=JetsamConfig())
        stage_step = plan.steps[0]
        assert "src/main.py" in stage_step.params["files"]
        assert "docs/readme.md" not in stage_step.params["files"]

    def test_exclude_pattern(self):
        state = _make_state(unstaged=["src/main.py", "src/generated.py"])
        plan = plan_save(state, plan_id="p_test", message="fix", exclude="*generated*", config=JetsamConfig())
        stage_step = plan.steps[0]
        assert "src/main.py" in stage_step.params["files"]
        assert "src/generated.py" not in stage_step.params["files"]

    def test_explicit_files(self):
        state = _make_state()
        plan = plan_save(state, plan_id="p_test", message="fix", files=["specific.py"], config=JetsamConfig())
        stage_step = plan.steps[0]
        assert stage_step.params["files"] == ["specific.py"]

    def test_explicit_files_with_exclude(self):
        state = _make_state()
        plan = plan_save(
            state, plan_id="p_test", message="fix",
            files=["keep.py", "generated.py"], exclude="*generated*", config=JetsamConfig(),
        )
        stage_step = plan.steps[0]
        assert stage_step.params["files"] == ["keep.py"]

    def test_auto_message(self):
        state = _make_state(unstaged=["src/parser.py"])
        plan = plan_save(state, plan_id="p_test", config=JetsamConfig())
        commit_step = next(s for s in plan.steps if s.action == "commit")
        assert "parser" in commit_step.params["message"]

    def test_nothing_to_commit(self):
        state = _make_state(staged=[], unstaged=[], untracked=[], dirty=False)
        plan = plan_save(state, plan_id="p_test", message="noop", config=JetsamConfig())
        assert any("No files" in w for w in plan.warnings)
        assert len(plan.steps) == 0  # should have no steps

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


class TestPlanSync:
    def test_feature_branch_rebase(self):
        state = _make_state(dirty=False)
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "fetch" in actions
        assert "rebase" in actions
        assert "push" in actions

    def test_default_branch_merge(self):
        state = _make_state(branch="main", dirty=False, ahead=0)
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "fetch" in actions
        assert "merge" in actions

    def test_dirty_stashes(self):
        state = _make_state(dirty=True)
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert actions[0] == "stash"
        assert actions[-1] == "stash_pop"

    def test_no_upstream(self):
        state = _make_state(upstream=None, dirty=False)
        plan = plan_sync(state, plan_id="p_test")
        rebase_step = next(s for s in plan.steps if s.action == "rebase")
        assert rebase_step.params["onto"] == "origin/main"

    def test_sync_hash_stable_when_ahead_behind_change(self):
        """Sync plan hash should NOT change when only ahead/behind change.

        This is the core bug: fetch updates remote refs which changes
        ahead/behind counts, causing stale_plan errors.
        """
        state1 = _make_state(ahead=0, behind=0, dirty=False)
        plan1 = plan_sync(state1, plan_id="p_test")

        state2 = _make_state(ahead=0, behind=3, dirty=False)
        plan2 = plan_sync(state2, plan_id="p_test")

        assert plan1.state_hash == plan2.state_hash

    def test_sync_hash_changes_on_local_state(self):
        """Sync plan hash SHOULD change when local state changes."""
        state1 = _make_state(dirty=False)
        plan1 = plan_sync(state1, plan_id="p_test")

        # Different branch = different hash
        state2 = _make_state(dirty=False, branch="other")
        plan2 = plan_sync(state2, plan_id="p_test")

        assert plan1.state_hash != plan2.state_hash

    def test_sync_hash_changes_on_dirty_state(self):
        """Sync plan hash SHOULD change when working tree becomes dirty."""
        state1 = _make_state(dirty=False, staged=[], unstaged=[], untracked=[])
        plan1 = plan_sync(state1, plan_id="p_test")

        state2 = _make_state(dirty=True, staged=[], unstaged=["new.py"], untracked=[])
        plan2 = plan_sync(state2, plan_id="p_test")

        assert plan1.state_hash != plan2.state_hash

    def test_sync_to_dict_includes_exclude_remote_tracking(self):
        """Sync plan's to_dict should include exclude_remote_tracking."""
        state = _make_state(dirty=False)
        plan = plan_sync(state, plan_id="p_test")
        d = plan.to_dict()
        assert d["exclude_remote_tracking"] is True

    def test_default_branch_ahead_only_fast_path(self):
        """Default branch, ahead only, clean tree → just push."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=False,
            staged=[], unstaged=[], untracked=[], ahead=1, behind=0,
        )
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert actions == ["push"]

    def test_default_branch_untracked_only_fast_path(self):
        """Untracked-only dirty state should not trigger stash, still takes fast path."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=True,
            staged=[], unstaged=[], untracked=["scratch.txt"], ahead=1, behind=0,
        )
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert actions == ["push"]
        assert "stash" not in actions

    def test_default_branch_ahead_and_behind_full_plan(self):
        """Default branch, ahead and behind → full plan with fetch/merge."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=False,
            staged=[], unstaged=[], untracked=[], ahead=1, behind=2,
        )
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "fetch" in actions
        assert "merge" in actions
        assert "push" in actions

    def test_default_branch_ahead_with_staged_changes(self):
        """Default branch with staged changes → full plan with stash."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=True,
            staged=["file.py"], unstaged=[], untracked=[], ahead=1, behind=0,
        )
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert actions[0] == "stash"
        assert actions[-1] == "stash_pop"
        assert "fetch" in actions
        assert "merge" in actions
        assert "push" in actions

    def test_default_branch_explicit_strategy_skips_fast_path(self):
        """Explicit strategy on default branch bypasses fast path."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=False,
            staged=[], unstaged=[], untracked=[], ahead=1, behind=0,
        )
        plan = plan_sync(state, plan_id="p_test", strategy="merge")
        actions = [s.action for s in plan.steps]
        assert "fetch" in actions
        assert "merge" in actions

    def test_default_branch_not_ahead_no_fast_path(self):
        """Default branch, not ahead → normal path (no fast path)."""
        state = _make_state(
            branch="main", upstream="origin/main", dirty=False,
            staged=[], unstaged=[], untracked=[], ahead=0, behind=0,
        )
        plan = plan_sync(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "fetch" in actions
        assert "merge" in actions
        assert "push" not in actions


class TestPlanFinish:
    def test_finish_hash_stable_when_ahead_behind_change(self):
        """Finish plan hash should NOT change when only ahead/behind change.

        plan_finish includes a fetch step, so it has the same race condition
        as plan_sync.
        """
        state1 = _make_state(ahead=0, behind=0, dirty=False)
        plan1 = plan_finish(state1, plan_id="p_test")

        state2 = _make_state(ahead=0, behind=3, dirty=False)
        plan2 = plan_finish(state2, plan_id="p_test")

        assert plan1.state_hash == plan2.state_hash
        assert plan1.exclude_remote_tracking is True


class TestPlanShip:
    def test_full_pipeline(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship it", config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "stage" in actions
        assert "commit" in actions
        assert "push" in actions
        assert "pr_create" in actions

    def test_with_existing_pr(self):
        from jetsam.core.state import PRInfo

        pr = PRInfo(number=42, state="open", title="existing")
        state = _make_state(pr=pr)
        plan = plan_ship(state, plan_id="p_test", message="update", config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "pr_update" in actions
        assert "pr_create" not in actions

    def test_behind_warning(self):
        state = _make_state(behind=3)
        plan = plan_ship(state, plan_id="p_test", message="ship", config=JetsamConfig())
        assert any("behind" in w for w in plan.warnings)

    def test_no_pr(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=False, config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "pr_create" not in actions
        assert "pr_update" not in actions

    def test_merge_into_self_warning(self):
        state = _make_state(branch="main", default_branch="main")
        plan = plan_ship(state, plan_id="p_test", message="ship", merge=True, config=JetsamConfig())
        assert any("itself" in w for w in plan.warnings)

    def test_to_dict(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship it", config=JetsamConfig())
        d = plan.to_dict()
        assert d["plan_id"] == "p_test"
        assert isinstance(d["steps"], list)
        assert all(isinstance(s, dict) for s in d["steps"])

    def test_files_parameter(self):
        """ship with files= scopes staging to listed files only."""
        state = _make_state(unstaged=["a.py", "b.py", "c.py"])
        plan = plan_ship(
            state, plan_id="p_test", message="ship",
            files=["a.py"], config=JetsamConfig(),
        )
        stage_step = next(s for s in plan.steps if s.action == "stage")
        assert stage_step.params["files"] == ["a.py"]

    def test_nothing_to_commit_push_only(self):
        """ship with nothing to commit but ahead>0 generates push-only plan."""
        state = _make_state(
            staged=[], unstaged=[], untracked=[], dirty=False, ahead=2,
        )
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=False, config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "stage" not in actions
        assert "commit" not in actions
        assert "push" in actions

    def test_nothing_to_commit_with_pr(self):
        """ship with nothing to commit, ahead>0, open_pr=True generates push+PR."""
        state = _make_state(
            staged=[], unstaged=[], untracked=[], dirty=False, ahead=2,
        )
        plan = plan_ship(state, plan_id="p_test", message="ship", config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "commit" not in actions
        assert "push" in actions
        assert "pr_create" in actions

    def test_nothing_to_commit_or_push_warns(self):
        """ship with nothing to commit, ahead=0, no PR returns warning."""
        state = _make_state(
            staged=[], unstaged=[], untracked=[], dirty=False, ahead=0,
        )
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=False, config=JetsamConfig())
        assert any("nothing" in w.lower() for w in plan.warnings)
        assert len(plan.steps) == 0

    def test_nothing_to_commit_ahead_zero_pr_only(self):
        """ship with nothing to commit, ahead=0, but PR requested creates PR."""
        state = _make_state(
            staged=[], unstaged=[], untracked=[], dirty=False, ahead=0,
        )
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=True, config=JetsamConfig())
        actions = [s.action for s in plan.steps]
        assert "commit" not in actions
        assert "pr_create" in actions

    def test_files_empty_list_same_as_none(self):
        """ship with files=[] behaves same as files=None."""
        state = _make_state()
        plan_with_none = plan_ship(state, plan_id="p1", message="ship", files=None, config=JetsamConfig())
        plan_with_empty = plan_ship(state, plan_id="p2", message="ship", files=[], config=JetsamConfig())
        actions_none = [s.action for s in plan_with_none.steps]
        actions_empty = [s.action for s in plan_with_empty.steps]
        assert actions_none == actions_empty

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
