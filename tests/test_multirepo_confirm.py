"""Regression tests for the multi-repo stale_plan bug.

A plan is built for the repo at the cwd where save/sync/etc. ran, and its
state_hash reflects that repo. The MCP `confirm(id)` tool used to call
`execute_plan(plan)` with no cwd, so `execute_plan` rebuilt state via
`build_state(cwd=None)` — which falls back to the server's fixed active_root,
NOT the plan's repo. In any session touching more than one repo, confirm
would rebuild state in the WRONG repo, the hashes would differ, and every
cross-repo confirm returned `stale_plan`.

The fix: the Plan records `repo_root`, persists it, and `confirm` executes
with `cwd=plan.repo_root`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from jetsam.core.executor import execute_plan
from jetsam.core.planner import plan_save
from jetsam.core.plans import PlanStore, generate_plan_id
from jetsam.core.state import build_state

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}


def _init_repo(path: Path) -> str:
    """Create a git repo with one commit. Returns its repo root per git."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True,
                   env=_GIT_ENV, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path,
                   check=True, capture_output=True)
    (path / "README.md").write_text("# repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True,
                   env=_GIT_ENV, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True,
                   env=_GIT_ENV, capture_output=True)
    return build_state(cwd=str(path)).repo_root


class TestMultiRepoConfirm:
    """The plan must validate/execute in its own repo, not a fixed default."""

    def test_plan_records_repo_root_and_executes_there(self, tmp_path: Path):
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        root_a = _init_repo(repo_a)
        _init_repo(repo_b)

        # Stage a change in A.
        (repo_a / "feature.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_a, check=True,
                       env=_GIT_ENV, capture_output=True)

        state = build_state(cwd=str(repo_a))
        plan = plan_save(state, plan_id="p_t", message="x")

        # The plan remembers which repo it was built for.
        assert plan.repo_root == state.repo_root == root_a

        # Executing in the plan's own repo succeeds (the fix path: confirm
        # passes cwd=plan.repo_root).
        ok = execute_plan(plan, cwd=plan.repo_root)
        assert ok.status == "ok", ok.to_dict()

        # And the commit actually landed in A.
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=repo_a, capture_output=True, text=True,
        )
        assert "x" in log.stdout

    def test_old_behavior_would_stale_in_wrong_repo(self, tmp_path: Path):
        """Documents the bug: executing the plan in the WRONG repo (as the old
        confirm did when build_state fell back to a different active_root)
        rebuilds state in B, the hashes differ, and the plan is rejected as
        stale before any step runs."""
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        _init_repo(repo_a)
        _init_repo(repo_b)

        (repo_a / "feature.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_a, check=True,
                       env=_GIT_ENV, capture_output=True)

        state = build_state(cwd=str(repo_a))
        plan = plan_save(state, plan_id="p_t", message="x")

        result = execute_plan(plan, cwd=str(repo_b))
        assert result.status == "failed"
        assert result.results[0].error == "stale_plan"

    def test_confirm_path_uses_plan_repo_root(self, tmp_path: Path):
        """Exercise the exact logic the MCP `confirm` tool now uses:
        load the plan from disk and execute with `cwd=plan.repo_root or None`.

        Persistence must round-trip repo_root, and the loaded plan must
        execute against its own repo even though the default cwd (None /
        process cwd) points elsewhere. With the old `execute_plan(plan)`
        (no cwd) this would stale whenever the process cwd != repo A.
        """
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        _init_repo(repo_a)
        _init_repo(repo_b)

        (repo_a / "feature.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_a, check=True,
                       env=_GIT_ENV, capture_output=True)

        state = build_state(cwd=str(repo_a))
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="x")

        # Persist via PlanStore (round-trips repo_root) and reload. The store
        # lives in a fixed per-user dir, independent of any repo/cwd (#17).
        store = PlanStore()
        store.save(plan)
        loaded = store.load(plan_id)
        assert loaded is not None
        assert loaded.repo_root == state.repo_root

        # This is exactly what confirm() now does.
        result = execute_plan(loaded, cwd=loaded.repo_root or None)
        assert result.status == "ok", result.to_dict()

    def test_confirm_tool_executes_in_plan_repo(self, tmp_path, monkeypatch):
        """End-to-end guard on the MCP `confirm` tool itself.

        This is the test that fails if edit #4 (confirm passing
        cwd=plan.repo_root) is reverted: it drives the *registered* confirm
        closure, with the server's PlanStore rooted at repo B (simulating a
        server whose active_root is B) while the plan was built in repo A.

        With the fix, confirm executes at plan.repo_root (A) and succeeds.
        With the old `execute_plan(plan)` (no cwd), the executor would rebuild
        state in the server's default repo, the hashes would differ, and the
        result would be stale_plan.
        """
        from mcp.server.fastmcp import FastMCP

        import jetsam.mcp.tools as tools
        from jetsam.mcp.tools import register_tools

        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        _init_repo(repo_a)
        _init_repo(repo_b)

        (repo_a / "feature.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_a, check=True,
                       env=_GIT_ENV, capture_output=True)

        state = build_state(cwd=str(repo_a))
        plan_id = generate_plan_id()
        plan = plan_save(state, plan_id=plan_id, message="x")

        # The store is per-user (not per-repo); confirm still executes in the
        # plan's own repo (A). Pin the module global so confirm uses this store.
        store_b = PlanStore()
        store_b.save(plan)
        monkeypatch.setattr(tools, "_plan_store", store_b)

        # Run from a cwd that is neither A nor B, to make the bug's fallback
        # path (build_state(cwd=None) -> process cwd) clearly wrong.
        monkeypatch.chdir(tmp_path)

        mcp = FastMCP("test")
        register_tools(mcp)
        confirm = mcp._tool_manager.get_tool("confirm").fn

        result = confirm(id=plan_id)
        assert result.get("status") == "ok", result

        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=repo_a, capture_output=True, text=True,
        )
        assert "x" in log.stdout
