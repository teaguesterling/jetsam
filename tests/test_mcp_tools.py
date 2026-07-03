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
        store = PlanStore()
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

        store = PlanStore()
        state = build_state(cwd=str(tmp_git_repo))
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="test")

        store.save(plan)
        assert store.load(plan_id) is not None

        store.delete(plan_id)
        assert store.load(plan_id) is None


class TestNewToolsRegistration:
    """Verify new tools register without errors."""

    def test_register_includes_new_tools(self):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "pr_comment" in tool_names
        assert "pr_review" in tool_names
        assert "pr_comments" in tool_names
        assert "issue_close" in tool_names


class TestCwdBinding:
    """Workflow verbs accept a `cwd` arg and operate on that repo instead of
    process cwd. Regression test for the bug 3/5 user personas hit where
    `status` returned the wrong repo's state because the verb silently
    dropped any path argument.
    """

    def test_status_honors_cwd_argument(
        self, tmp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Make a SECOND repo at a different path.
        other_repo = tmp_path / "other_repo"
        other_repo.mkdir()
        subprocess.run(["git", "init", "-b", "feature"], cwd=str(other_repo), check=True)
        subprocess.run(["git", "config", "user.email", "x@y"], cwd=str(other_repo), check=True)
        subprocess.run(["git", "config", "user.name", "x"], cwd=str(other_repo), check=True)
        (other_repo / "f").write_text("x")
        subprocess.run(["git", "add", "."], cwd=str(other_repo), check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(other_repo), check=True)

        # Set process cwd / env to the FIRST repo. Without the cwd
        # parameter, status would return state for tmp_git_repo (branch
        # 'main'). With cwd=other_repo, it should return state for
        # other_repo (branch 'feature').
        monkeypatch.chdir(tmp_git_repo)
        monkeypatch.delenv("GIT_DIR", raising=False)
        monkeypatch.delenv("GIT_WORK_TREE", raising=False)

        from jetsam.core.state import build_state

        # No cwd: gets the first repo (tmp_git_repo, branch 'main').
        state_default = build_state()
        assert state_default.branch == "main"

        # With cwd=other_repo: gets the other repo (branch 'feature').
        state_other = build_state(cwd=str(other_repo))
        assert state_other.branch == "feature"

    def test_mcp_status_signature_includes_cwd(self):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)
        status_tool = mcp._tool_manager._tools["status"]
        params = status_tool.parameters.get("properties", {})
        assert "cwd" in params, (
            "status() should expose `cwd` as an MCP parameter — without it, "
            "workflow verbs silently fall back to process cwd."
        )

    def test_mcp_save_signature_includes_cwd(self):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)
        save_tool = mcp._tool_manager._tools["save"]
        params = save_tool.parameters.get("properties", {})
        assert "cwd" in params

    def test_mcp_sync_signature_includes_cwd(self):
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)
        sync_tool = mcp._tool_manager._tools["sync"]
        params = sync_tool.parameters.get("properties", {})
        assert "cwd" in params


class TestErrorFormats:
    """Verify all error paths return standard JetsamError dicts."""

    def test_log_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """log() should return a JetsamError dict, not a list, on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        log_fn = mcp._tool_manager._tools["log"].fn
        result = log_fn(n=10, branch="nonexistent-branch-xyz")

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result

    def test_diff_stat_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """diff() in stat mode should return JetsamError dict on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        diff_fn = mcp._tool_manager._tools["diff"].fn
        result = diff_fn(target="nonexistent-ref-xyz", stat=True, staged=False)

        assert isinstance(result, dict)
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result

    def test_diff_full_error_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """diff() in full mode should return JetsamError dict on error."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        diff_fn = mcp._tool_manager._tools["diff"].fn
        result = diff_fn(target="nonexistent-ref-xyz", stat=False, staged=False)

        assert isinstance(result, dict)
        assert result["error"] == "git_error"
        assert "message" in result
        assert "recoverable" in result


    def test_pr_view_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        pr_view_fn = mcp._tool_manager._tools["pr_view"].fn
        result = pr_view_fn(branch=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result
        assert "recoverable" in result

    def test_pr_list_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        pr_list_fn = mcp._tool_manager._tools["pr_list"].fn
        result = pr_list_fn(state="open", author=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result
        assert "recoverable" in result

    def test_checks_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        checks_fn = mcp._tool_manager._tools["checks"].fn
        result = checks_fn(pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_issues_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        issues_fn = mcp._tool_manager._tools["issues"].fn
        result = issues_fn(state="open", labels=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_comments_no_platform_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_comments"].fn
        result = fn(branch=None, pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_comment_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_comment"].fn
        result = fn(body="test", branch=None, pr_number=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_pr_review_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["pr_review"].fn
        result = fn(event="approve", body="", branch=None, pr_number=None)

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_issue_close_no_platform_returns_jetsam_error(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        fn = mcp._tool_manager._tools["issue_close"].fn
        result = fn(number=999, comment=None, reason="completed")

        assert isinstance(result, dict)
        assert result["error"] == "no_platform"
        assert "message" in result

    def test_checks_no_pr_returns_jetsam_error_dict(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """checks() should return JetsamError dict when no PR exists."""
        monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))

        from unittest.mock import MagicMock

        from mcp.server.fastmcp import FastMCP

        mock_platform = MagicMock()
        mock_platform.pr_for_branch.return_value = None
        monkeypatch.setattr(mcp_tools, "_get_platform", lambda _: mock_platform)

        mcp = FastMCP("test")
        mcp_tools.register_tools(mcp)

        checks_fn = mcp._tool_manager._tools["checks"].fn
        result = checks_fn(pr_number=None)

        assert isinstance(result, dict), "Error should be a dict, not a list"
        assert result["error"] == "no_pr"
        assert "message" in result
        assert "recoverable" in result


class TestErrorHelpers:
    """Test the error helper functions produce standard JetsamError format."""

    def test_no_platform_error(self):
        from jetsam.mcp.tools import _no_platform_error

        result = _no_platform_error()
        assert result["error"] == "no_platform"
        assert "message" in result
        assert result["recoverable"] is False

    def test_no_pr_error(self):
        from jetsam.mcp.tools import _no_pr_error

        result = _no_pr_error("feature/foo")
        assert result["error"] == "no_pr"
        assert "feature/foo" in result["message"]
        assert result["recoverable"] is True
