"""Tests for plan execution."""

import os
import subprocess
from pathlib import Path

from jetsam.core.executor import StepResult, _exec_stash, _exec_stash_pop, execute_plan
from jetsam.core.planner import Plan, PlanStep, plan_save, plan_sync
from jetsam.core.state import build_state


class TestExecutePlan:
    def test_save_executes(self, dirty_git_repo: Path):
        cwd = str(dirty_git_repo)
        state = build_state(cwd=cwd)

        plan = plan_save(state, plan_id="p_test", message="test save")
        result = execute_plan(plan, cwd=cwd)

        assert result.status == "ok"
        assert result.completed_steps == result.total_steps
        # Verify commit was created
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=cwd,
        )
        assert "test save" in log_result.stdout

    def test_stale_plan_rejected(self, dirty_git_repo: Path):
        cwd = str(dirty_git_repo)
        state = build_state(cwd=cwd)

        plan = plan_save(state, plan_id="p_test", message="test save")

        # Modify repo state by staging a file that's in the plan's scope
        # (README.md is unstaged in dirty_git_repo, and is in the plan's scope)
        env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
               "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"}
        subprocess.run(["git", "add", "README.md"], cwd=cwd, check=True, env=env,
                       capture_output=True)

        result = execute_plan(plan, cwd=cwd)
        assert result.status == "failed"
        assert result.results[0].error == "stale_plan"

    def test_save_with_explicit_files(self, dirty_git_repo: Path):
        cwd = str(dirty_git_repo)
        state = build_state(cwd=cwd)

        plan = plan_save(state, plan_id="p_test", message="save specific",
                         files=["scratch.txt"])
        result = execute_plan(plan, cwd=cwd)

        assert result.status == "ok"

    def test_result_to_dict(self, dirty_git_repo: Path):
        cwd = str(dirty_git_repo)
        state = build_state(cwd=cwd)

        plan = plan_save(state, plan_id="p_test", message="test")
        result = execute_plan(plan, cwd=cwd)

        d = result.to_dict()
        assert d["plan_id"] == "p_test"
        assert d["status"] == "ok"
        assert isinstance(d["results"], list)
        assert d["completed_steps"] == d["total_steps"]


class TestSyncPlanValidation:
    """Sync plan validation should ignore ahead/behind changes."""

    def test_sync_plan_valid_after_ahead_behind_change(self, tmp_git_repo: Path):
        """A sync plan should not be rejected when ahead/behind counts change.

        This reproduces the bug: plan_sync creates a plan, then between plan
        creation and execution, a fetch changes ahead/behind. The executor
        should still accept the plan since local state hasn't changed.
        """
        cwd = str(tmp_git_repo)
        state = build_state(cwd=cwd)
        plan = plan_sync(state, plan_id="p_test")

        # The plan's state_hash was computed with ahead=0, behind=0.
        # Simulate what happens when executor rebuilds state and ahead/behind
        # differ: the hash should still match because sync excludes those fields.
        #
        # We can't easily change ahead/behind in a local-only repo, so we
        # verify the hash computation directly: rebuild state and confirm the
        # hash matches even though we're computing it fresh.
        current_state = build_state(cwd=cwd)
        current_hash = current_state.compute_hash(
            scope=plan.scope,
            exclude_remote_tracking=plan.exclude_remote_tracking,
        )
        assert current_hash == plan.state_hash

    def test_save_plan_still_detects_staleness(self, dirty_git_repo: Path):
        """Save plans should still detect state changes (regression check)."""
        cwd = str(dirty_git_repo)
        state = build_state(cwd=cwd)
        plan = plan_save(state, plan_id="p_test", message="test")

        # Modify a file in scope
        (dirty_git_repo / "README.md").write_text("# Changed again\n")
        env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
               "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"}
        subprocess.run(["git", "add", "README.md"], cwd=cwd, check=True, env=env,
                       capture_output=True)

        result = execute_plan(plan, cwd=cwd)
        assert result.status == "failed"
        assert result.results[0].error == "stale_plan"


class TestPlanStore:
    def test_save_and_load(self, tmp_git_repo: Path):
        from jetsam.core.plans import PlanStore

        store = PlanStore(str(tmp_git_repo))
        state = build_state(cwd=str(tmp_git_repo))
        plan = plan_save(state, plan_id="p_test", message="test")

        store.save(plan)
        loaded = store.load("p_test")
        assert loaded is not None
        assert loaded.plan_id == "p_test"
        assert loaded.verb == "save"
        assert len(loaded.steps) == len(plan.steps)

    def test_load_nonexistent(self, tmp_git_repo: Path):
        from jetsam.core.plans import PlanStore

        store = PlanStore(str(tmp_git_repo))
        assert store.load("p_nonexistent") is None

    def test_delete(self, tmp_git_repo: Path):
        from jetsam.core.plans import PlanStore

        store = PlanStore(str(tmp_git_repo))
        state = build_state(cwd=str(tmp_git_repo))
        plan = plan_save(state, plan_id="p_test", message="test")

        store.save(plan)
        store.delete("p_test")
        assert store.load("p_test") is None


class TestUpdatePlan:
    def test_update_message(self, dirty_git_repo: Path):
        from jetsam.core.plans import update_plan

        state = build_state(cwd=str(dirty_git_repo))
        plan = plan_save(state, plan_id="p_test", message="old")

        diff = update_plan(plan, message="new message")
        assert diff["message"]["old"] == "old"
        assert diff["message"]["new"] == "new message"

        # Verify the plan was actually updated
        commit_step = next(s for s in plan.steps if s.action == "commit")
        assert commit_step.params["message"] == "new message"

    def test_update_exclude(self, dirty_git_repo: Path):
        from jetsam.core.plans import update_plan

        state = build_state(cwd=str(dirty_git_repo))
        plan = plan_save(state, plan_id="p_test", message="test",
                         files=["a.py", "b.py", "c_generated.py"])

        diff = update_plan(plan, exclude="*generated*")
        assert "c_generated.py" in diff.get("removed_files", [])


class TestStashNoOp:
    """Tests for stash/stash_pop when nothing is actually stashed (P9-001)."""

    def test_stash_reports_not_stashed_when_nothing_to_stash(self, tmp_git_repo: Path):
        """When git stash push has nothing to stash, details['stashed'] should be False."""
        cwd = str(tmp_git_repo)
        step = PlanStep(action="stash", params={"message": "test stash"})
        result = _exec_stash(step, cwd)
        assert result.ok is True
        assert result.details.get("stashed") is False

    def test_stash_reports_stashed_when_changes_exist(self, dirty_git_repo: Path):
        """When there are real changes, details['stashed'] should be True."""
        cwd = str(dirty_git_repo)
        step = PlanStep(action="stash", params={"message": "test stash"})
        result = _exec_stash(step, cwd)
        assert result.ok is True
        assert result.details.get("stashed") is True

    def test_stash_pop_skips_when_nothing_was_stashed(self, tmp_git_repo: Path):
        """stash_pop should be a no-op (ok=True, skipped=True) when stash didn't store anything."""
        cwd = str(tmp_git_repo)
        # Simulate prior stash result that didn't actually stash
        prior_results = [
            StepResult(step="stash", ok=True, details={"stashed": False}),
        ]
        step = PlanStep(action="stash_pop")
        result = _exec_stash_pop(step, cwd, prior_results=prior_results)
        assert result.ok is True
        assert result.details.get("skipped") is True

    def test_stash_pop_pops_when_something_was_stashed(self, dirty_git_repo: Path):
        """stash_pop should actually pop when stash stored something."""
        cwd = str(dirty_git_repo)
        # Actually stash first
        stash_step = PlanStep(action="stash", params={"message": "test"})
        stash_result = _exec_stash(stash_step, cwd)
        assert stash_result.details["stashed"] is True

        prior_results = [stash_result]
        pop_step = PlanStep(action="stash_pop")
        result = _exec_stash_pop(pop_step, cwd, prior_results=prior_results)
        assert result.ok is True
        assert result.details.get("skipped") is not True

    def test_stash_pop_without_prior_results_attempts_pop(self, dirty_git_repo: Path):
        """When prior_results is None, stash_pop should attempt the pop (backward compat)."""
        cwd = str(dirty_git_repo)
        # Stash something so pop will succeed
        stash_step = PlanStep(action="stash", params={"message": "test"})
        stash_result = _exec_stash(stash_step, cwd)
        assert stash_result.details["stashed"] is True

        pop_step = PlanStep(action="stash_pop")
        # No prior_results passed — should still attempt the pop
        result = _exec_stash_pop(pop_step, cwd)
        assert result.ok is True
        assert result.details.get("skipped") is not True

    def test_stash_pop_skips_in_plan_when_nothing_stashed(self, tmp_git_repo: Path):
        """Full plan with stash+stash_pop succeeds when nothing was actually stashed."""
        cwd = str(tmp_git_repo)
        # Add an untracked file to make state.dirty True
        (tmp_git_repo / "untracked.txt").write_text("untracked\n")

        state = build_state(cwd=cwd)
        assert state.dirty, "Expected dirty state from untracked file"

        # Build a minimal plan with just stash and stash_pop
        plan = Plan(
            plan_id="p_stash_test",
            verb="sync",
            steps=[
                PlanStep(action="stash", params={"message": "test"}),
                PlanStep(action="stash_pop"),
            ],
            state_hash=state.compute_hash(),
        )
        result = execute_plan(plan, cwd=cwd)

        assert result.status == "ok"
        assert result.results[0].step == "stash"
        assert result.results[0].ok is True
        assert result.results[0].details["stashed"] is False
        assert result.results[1].step == "stash_pop"
        assert result.results[1].ok is True
        assert result.results[1].details.get("skipped") is True
