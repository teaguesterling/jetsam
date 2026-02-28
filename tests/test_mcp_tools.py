"""Tests for MCP tool functions.

Tests the tool functions directly (not via MCP protocol) since they're
the same operations exposed through both CLI and MCP interfaces.
"""

import subprocess
from pathlib import Path

import pytest

from jetsam.core.plans import PlanStore
from jetsam.mcp import tools as mcp_tools


@pytest.fixture(autouse=True)
def _reset_plan_store():
    """Reset the module-level plan store between tests."""
    mcp_tools._plan_store = None
    yield
    mcp_tools._plan_store = None


@pytest.fixture
def git_env(tmp_git_repo: Path) -> dict[str, str]:
    """Set up environment so git commands use the tmp repo."""
    return {
        "GIT_DIR": str(tmp_git_repo / ".git"),
        "GIT_WORK_TREE": str(tmp_git_repo),
    }


class TestStatusTool:
    def test_returns_state(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        # Call the status function directly
        from jetsam.core.state import build_state
        state = build_state()
        result = state.to_dict()

        assert result["branch"] == "main"
        assert result["dirty"] is False


class TestSaveTool:
    def test_returns_plan(self, dirty_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(dirty_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(dirty_git_repo))

        from jetsam.core.planner import plan_save
        from jetsam.core.plans import generate_plan_id
        from jetsam.core.state import build_state

        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="test save")
        result = plan.to_dict()

        assert "plan_id" in result
        assert "steps" in result
        assert any(s["action"] == "commit" for s in result["steps"])

    def test_confirm_executes(self, dirty_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(dirty_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(dirty_git_repo))

        from jetsam.core.executor import execute_plan
        from jetsam.core.planner import plan_save
        from jetsam.core.plans import generate_plan_id
        from jetsam.core.state import build_state

        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="mcp test save")

        # Store and retrieve
        store = PlanStore(str(dirty_git_repo))
        store.save(plan)

        loaded = store.load(plan_id)
        assert loaded is not None

        result = execute_plan(loaded)
        assert result.status == "ok"

        # Verify commit
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=str(dirty_git_repo),
        )
        assert "mcp test save" in log_result.stdout


class TestGitPassthrough:
    def test_version(self):
        from jetsam.git.wrapper import run_git_sync

        result = run_git_sync(["--version"])
        assert result.ok
        assert "git version" in result.stdout

    def test_log(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from jetsam.git.wrapper import run_git_sync

        result = run_git_sync(["log", "--oneline", "-1"])
        assert result.ok
        assert "initial" in result.stdout


class TestLogTool:
    def test_returns_entries(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))


        from jetsam.git.parsers import parse_log
        from jetsam.git.wrapper import run_git_sync

        fmt = "%H%x00%h%x00%an%x00%aI%x00%s"
        result = run_git_sync(["log", f"--format={fmt}", "-10"])
        assert result.ok

        entries = parse_log(result.stdout)
        assert len(entries) >= 1
        assert entries[0].message == "initial"


class TestDiffTool:
    def test_stat(self, dirty_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GIT_DIR", str(dirty_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(dirty_git_repo))


        from jetsam.git.parsers import parse_diff_numstat
        from jetsam.git.wrapper import run_git_sync

        result = run_git_sync(["diff", "--numstat"])
        assert result.ok

        stat = parse_diff_numstat(result.stdout)
        assert stat.files_changed > 0


class TestPlanWorkflow:
    def test_save_modify_confirm(self, dirty_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        """Test the full plan → modify → confirm workflow."""
        monkeypatch.setenv("GIT_DIR", str(dirty_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(dirty_git_repo))

        from jetsam.core.executor import execute_plan
        from jetsam.core.planner import plan_save
        from jetsam.core.plans import generate_plan_id, update_plan
        from jetsam.core.state import build_state

        # Create plan
        state = build_state()
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="original msg",
                         files=["staged.py", "README.md"])

        # Modify message
        diff = update_plan(plan, message="updated msg")
        assert diff["message"]["new"] == "updated msg"

        # Confirm
        result = execute_plan(plan)
        assert result.status == "ok"

        # Verify the updated message was used
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=str(dirty_git_repo),
        )
        assert "updated msg" in log_result.stdout

    def test_cancel_plan(self, tmp_git_repo: Path):
        """Test that cancelling a plan removes it."""
        from jetsam.core.planner import plan_save
        from jetsam.core.plans import generate_plan_id
        from jetsam.core.state import build_state

        store = PlanStore(str(tmp_git_repo))
        state = build_state(cwd=str(tmp_git_repo))
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="test")

        store.save(plan)
        assert store.load(plan_id) is not None

        store.delete(plan_id)
        assert store.load(plan_id) is None
