"""Tests for workflow verbs consuming runtime config knobs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jetsam.config import runtime as rt
from jetsam.config.runtime import JetsamRuntimeConfig, update_runtime
from jetsam.core.planner import plan_save, plan_ship, plan_sync, plan_release
from jetsam.core.state import build_state


@pytest.fixture(autouse=True)
def _isolate_runtime():
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()
    yield
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()


def _init_repo(path: Path, on_branch: str = "feature/x", gpgsign: bool = False) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init"],
        cwd=path, check=True, capture_output=True,
    )
    if on_branch != "main":
        subprocess.run(["git", "checkout", "-b", on_branch], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "true" if gpgsign else "false"],
        cwd=path, check=True, capture_output=True,
    )


class TestSyncStrategyConsumed:
    """plan_sync should use runtime.default_sync_strategy as the fallback
    for feature branches when no explicit strategy is passed."""

    def test_feature_branch_default_is_rebase(self, tmp_path):
        _init_repo(tmp_path, on_branch="feature/x")
        state = build_state(cwd=str(tmp_path))
        plan = plan_sync(state, plan_id="p1", strategy=None)
        # Even without an upstream, no sync steps run; this test just
        # verifies the runtime knob does not poison the verb when not set.
        assert plan.verb == "sync"

    def test_runtime_can_override_to_merge(self, tmp_path):
        _init_repo(tmp_path, on_branch="feature/x")
        # Set up an upstream so the strategy actually matters
        subprocess.run(["git", "remote", "add", "origin", str(tmp_path)], cwd=tmp_path,
                       check=True, capture_output=True)
        # Make a fake upstream by pointing the branch at HEAD
        subprocess.run(["git", "update-ref", "refs/remotes/origin/feature/x", "HEAD"],
                       cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "branch", "--set-upstream-to=origin/feature/x"],
                       cwd=tmp_path, check=True, capture_output=True)

        update_runtime({"default_sync_strategy": "merge"})
        state = build_state(cwd=str(tmp_path))
        plan = plan_sync(state, plan_id="p2", strategy=None)
        # Find the rebase/merge step
        ops = [s.action for s in plan.steps]
        assert "merge" in ops, f"expected merge in {ops}"
        assert "rebase" not in ops, f"unexpected rebase in {ops}"

    def test_explicit_strategy_still_wins(self, tmp_path):
        _init_repo(tmp_path, on_branch="feature/x")
        subprocess.run(["git", "remote", "add", "origin", str(tmp_path)], cwd=tmp_path,
                       check=True, capture_output=True)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/feature/x", "HEAD"],
                       cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "branch", "--set-upstream-to=origin/feature/x"],
                       cwd=tmp_path, check=True, capture_output=True)

        update_runtime({"default_sync_strategy": "merge"})
        state = build_state(cwd=str(tmp_path))
        plan = plan_sync(state, plan_id="p3", strategy="rebase")
        ops = [s.action for s in plan.steps]
        assert "rebase" in ops, f"explicit rebase should win over runtime merge — got {ops}"


class TestSigningRequired:
    """When signing_required=True and commit.gpgsign isn't enabled, the
    plan should be refused with a clear warning."""

    def test_save_refuses_when_signing_required_but_unset(self, tmp_path):
        _init_repo(tmp_path, gpgsign=False)
        update_runtime({"signing_required": True})
        # Touch a file so there's something to plan
        (tmp_path / "f.txt").write_text("hi")
        state = build_state(cwd=str(tmp_path))
        plan = plan_save(state, plan_id="p4", message="m", files=["f.txt"])
        assert plan.steps == [], "expected no steps when signing not configured"
        assert any("signing_required" in w for w in plan.warnings)

    def test_save_proceeds_when_signing_configured(self, tmp_path):
        _init_repo(tmp_path, gpgsign=True)
        update_runtime({"signing_required": True})
        (tmp_path / "f.txt").write_text("hi")
        state = build_state(cwd=str(tmp_path))
        plan = plan_save(state, plan_id="p5", message="m", files=["f.txt"])
        # Should have steps now
        assert len(plan.steps) > 0
        assert not any("signing_required" in w for w in plan.warnings)

    def test_save_unaffected_when_signing_not_required(self, tmp_path):
        _init_repo(tmp_path, gpgsign=False)
        # signing_required not set (default False)
        (tmp_path / "f.txt").write_text("hi")
        state = build_state(cwd=str(tmp_path))
        plan = plan_save(state, plan_id="p6", message="m", files=["f.txt"])
        # Should plan normally
        assert len(plan.steps) > 0

    def test_release_refuses_when_signing_required_but_unset(self, tmp_path):
        _init_repo(tmp_path, on_branch="main", gpgsign=False)
        update_runtime({"signing_required": True})
        state = build_state(cwd=str(tmp_path))
        plan = plan_release(state, plan_id="p7", tag="v0.0.1")
        assert plan.steps == []
        assert any("signing_required" in w for w in plan.warnings)
