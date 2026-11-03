"""Every workspace tool resolves its root explicitly, or fails loudly.

The resolution order is `cwd=` argument, then runtime `active_root`, then an
error.  There is no implicit read of the server's process cwd, because that
is how a tool answers confidently about a repository nobody asked about:
measured 2026-11-03, with `active_root` pointing at one repo, `log()` and
`diff()` still answered for the server's own directory.

The plan-store tools and `config` are exempt.  The plan store is a fixed
per-user directory since issue #17, and `confirm` executes with the repo
root recorded in the plan.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jetsam.config import runtime as rt
from jetsam.config.runtime import JetsamRuntimeConfig, update_runtime


@pytest.fixture(autouse=True)
def _isolate_runtime():
    """Reset the module singleton + seed between tests so order doesn't matter."""
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()
    yield
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()


@pytest.fixture(autouse=True)
def _no_git_env(monkeypatch: pytest.MonkeyPatch):
    """Git reads GIT_DIR/GIT_WORK_TREE ahead of cwd.

    Another test module sets both.  Left set, a cwd test passes whether or
    not cwd was ever threaded through, so clear them here.
    """
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


def _make_repo(path: Path, message: str) -> Path:
    """Create a repo with one commit whose subject identifies the repo."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", message],
        cwd=path, check=True, capture_output=True,
    )
    return path


@pytest.fixture
def tool():
    """Return a lookup for the registered MCP tool functions."""
    from mcp.server.fastmcp import FastMCP

    from jetsam.mcp.tools import register_tools

    server = FastMCP("test")
    register_tools(server)
    return lambda name: server._tool_manager._tools[name].fn


@pytest.fixture
def two_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Repo A is the target; repo B is the server's cwd, and is a valid repo.

    B being a real repo is the point: the failure this guards against is not
    "server outside a repo", it is "server inside the wrong repo".
    """
    repo_a = _make_repo(tmp_path / "a", "commit-in-a")
    repo_b = _make_repo(tmp_path / "b", "commit-in-b")
    monkeypatch.chdir(repo_b)
    return repo_a, repo_b


class TestGitPassthroughTakesCwd:
    def test_cwd_argument_targets_that_repo(self, tool, two_repos):
        repo_a, _ = two_repos
        result = tool("git")(args=["rev-parse", "--show-toplevel"], cwd=str(repo_a))
        assert result["ok"], result
        assert Path(result["stdout"].strip()).resolve() == repo_a.resolve()

    def test_active_root_applies_when_cwd_omitted(self, tool, two_repos):
        repo_a, _ = two_repos
        update_runtime({"active_root": str(repo_a)})
        result = tool("git")(args=["rev-parse", "--show-toplevel"])
        assert result["ok"], result
        assert Path(result["stdout"].strip()).resolve() == repo_a.resolve()


class TestLogAndDiffHonorActiveRoot:
    """Both take `cwd` already, but passed it straight to run_git_sync."""

    def test_log_uses_active_root(self, tool, two_repos):
        repo_a, _ = two_repos
        update_runtime({"active_root": str(repo_a)})
        entries = tool("log")(n=1)
        assert isinstance(entries, list), entries
        assert entries[0]["message"] == "commit-in-a"

    def test_diff_uses_active_root(self, tool, two_repos):
        repo_a, _ = two_repos
        (repo_a / "changed.txt").write_text("x\n")
        subprocess.run(["git", "add", "changed.txt"], cwd=repo_a, check=True, capture_output=True)
        update_runtime({"active_root": str(repo_a)})

        result = tool("diff")(staged=True)
        assert result.get("files_changed") == 1, result


class TestNoRootIsAnError:
    """With no cwd and no active_root, a tool must not read the process cwd."""

    @pytest.mark.parametrize("name,kwargs", [
        ("status", {}),
        ("log", {"n": 1}),
        ("diff", {}),
        ("git", {"args": ["rev-parse", "--show-toplevel"]}),
    ])
    def test_bare_call_returns_no_root_error(self, tool, two_repos, name, kwargs):
        result = tool(name)(**kwargs)

        assert isinstance(result, dict), f"{name} returned {type(result).__name__}"
        assert result.get("error") == "no_root", (
            f"{name} answered instead of refusing: {str(result)[:200]}"
        )
        # The refusal has to name both ways out, or the caller cannot act on
        # it.  Either field may carry them; what matters is that the payload
        # does.
        payload = result["message"] + " " + result.get("suggested_action", "")
        assert "cwd" in payload and "active_root" in payload, result

    def test_error_does_not_leak_the_servers_repo(self, tool, two_repos):
        _, repo_b = two_repos
        result = tool("status")()
        assert str(repo_b) not in str(result), (
            "the refusal must not report the server's own repo as the answer"
        )


class TestExemptTools:
    """Tools that touch no workspace keep working with no root set."""

    def test_config_works_without_a_root(self, tool):
        result = tool("config")()
        assert result["active_root"] is None

    def test_show_plan_reports_plan_not_found_not_no_root(self, tool, two_repos):
        result = tool("show_plan")(id="p_deadbeef")
        assert result.get("error") != "no_root", result

    def test_cancel_works_without_a_root(self, tool, two_repos):
        result = tool("cancel")(id="p_deadbeef")
        assert result.get("error") != "no_root", result


class TestExplicitCwdWins:
    """Control: this already held, and must keep holding."""

    def test_cwd_beats_active_root(self, tool, two_repos):
        repo_a, repo_b = two_repos
        update_runtime({"active_root": str(repo_a)})
        entries = tool("log")(n=1, cwd=str(repo_b))
        assert entries[0]["message"] == "commit-in-b"
