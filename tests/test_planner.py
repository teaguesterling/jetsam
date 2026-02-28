"""Tests for plan generation."""

from jetsam.core.planner import plan_save, plan_ship, plan_sync
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
        plan = plan_save(state, plan_id="p_test", message="fix bug")
        assert plan.verb == "save"
        assert len(plan.steps) == 2  # stage + commit
        assert plan.steps[0].action == "stage"
        assert plan.steps[1].action == "commit"
        assert plan.steps[1].params["message"] == "fix bug"

    def test_include_pattern(self):
        state = _make_state(unstaged=["src/main.py", "tests/test_main.py", "docs/readme.md"])
        plan = plan_save(state, plan_id="p_test", message="fix", include="src/*.py")
        stage_step = plan.steps[0]
        assert "src/main.py" in stage_step.params["files"]
        assert "docs/readme.md" not in stage_step.params["files"]

    def test_exclude_pattern(self):
        state = _make_state(unstaged=["src/main.py", "src/generated.py"])
        plan = plan_save(state, plan_id="p_test", message="fix", exclude="*generated*")
        stage_step = plan.steps[0]
        assert "src/main.py" in stage_step.params["files"]
        assert "src/generated.py" not in stage_step.params["files"]

    def test_explicit_files(self):
        state = _make_state()
        plan = plan_save(state, plan_id="p_test", message="fix", files=["specific.py"])
        stage_step = plan.steps[0]
        assert stage_step.params["files"] == ["specific.py"]

    def test_auto_message(self):
        state = _make_state(unstaged=["src/parser.py"])
        plan = plan_save(state, plan_id="p_test")
        commit_step = next(s for s in plan.steps if s.action == "commit")
        assert "parser" in commit_step.params["message"]

    def test_nothing_to_commit(self):
        state = _make_state(staged=[], unstaged=[], untracked=[], dirty=False)
        plan = plan_save(state, plan_id="p_test", message="noop")
        assert any("No files" in w for w in plan.warnings)


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


class TestPlanShip:
    def test_full_pipeline(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship it")
        actions = [s.action for s in plan.steps]
        assert "stage" in actions
        assert "commit" in actions
        assert "push" in actions
        assert "pr_create" in actions

    def test_with_existing_pr(self):
        from jetsam.core.state import PRInfo

        pr = PRInfo(number=42, state="open", title="existing")
        state = _make_state(pr=pr)
        plan = plan_ship(state, plan_id="p_test", message="update")
        actions = [s.action for s in plan.steps]
        assert "pr_update" in actions
        assert "pr_create" not in actions

    def test_behind_warning(self):
        state = _make_state(behind=3)
        plan = plan_ship(state, plan_id="p_test", message="ship")
        assert any("behind" in w for w in plan.warnings)

    def test_no_pr(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship", open_pr=False)
        actions = [s.action for s in plan.steps]
        assert "pr_create" not in actions
        assert "pr_update" not in actions

    def test_merge_into_self_warning(self):
        state = _make_state(branch="main", default_branch="main")
        plan = plan_ship(state, plan_id="p_test", message="ship", merge=True)
        assert any("itself" in w for w in plan.warnings)

    def test_to_dict(self):
        state = _make_state()
        plan = plan_ship(state, plan_id="p_test", message="ship it")
        d = plan.to_dict()
        assert d["plan_id"] == "p_test"
        assert isinstance(d["steps"], list)
        assert all(isinstance(s, dict) for s in d["steps"])
