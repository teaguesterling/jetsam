"""Tests for plan execution."""

import os
import subprocess
from pathlib import Path

from jetsam.core.executor import execute_plan
from jetsam.core.planner import plan_save
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
