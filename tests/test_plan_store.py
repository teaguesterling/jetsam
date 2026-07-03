"""Tests for the per-user PlanStore location and plan_id validation.

Covers issue #17 (the plan store was a cwd/repo-pinned singleton, so a plan
saved for repo A could be invisible when confirm loaded from a store resolved
to repo B -> plan_not_found) and the issue #19 input-validation item (plan_id
must be validated before it is joined into a filesystem path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jetsam.core.planner import Plan, PlanStep
from jetsam.core.plans import PlanStore, default_plans_dir, generate_plan_id


def _make_plan(plan_id: str, repo_root: str) -> Plan:
    return Plan(
        plan_id=plan_id,
        verb="save",
        steps=[PlanStep(action="commit", params={"message": "x"})],
        state_hash="deadbeef",
        repo_root=repo_root,
    )


class TestPerUserLocation:
    def test_survives_cwd_change_between_save_and_load(self, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch):
        """The #17 regression: a plan saved for repo A while the process cwd is
        A must still be found by a fresh store instance after the cwd moves to
        repo B. The store location is per-user, not per-repo/cwd."""
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repo_a.mkdir()
        repo_b.mkdir()

        plan_id = generate_plan_id()
        plan = _make_plan(plan_id, repo_root=str(repo_a))

        monkeypatch.chdir(repo_a)
        store = PlanStore()
        store.save(plan)
        saved_path = store.plans_dir / f"{plan_id}.json"
        assert saved_path.exists()

        # Simulate a different cwd / server restart: move away and rebuild the
        # store from scratch. With the old cwd-pinned store this would resolve
        # to repo B and miss the plan.
        monkeypatch.chdir(repo_b)
        fresh = PlanStore()
        loaded = fresh.load(plan_id)
        assert loaded is not None
        assert loaded.plan_id == plan_id
        assert loaded.repo_root == str(repo_a)

        # And the plan is stored under the per-user state dir, never under any
        # repo's .jetsam/.
        assert saved_path == default_plans_dir() / f"{plan_id}.json"
        assert ".jetsam" not in saved_path.parts
        assert str(repo_a) not in str(saved_path)
        assert str(repo_b) not in str(saved_path)

    def test_no_cwd_relative_store_when_not_a_repo(self, tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch):
        """Building the store when cwd is not a repo must resolve to the
        absolute per-user dir, never a relative ``.jetsam/plans``."""
        monkeypatch.chdir(tmp_path)  # not a git repo
        store = PlanStore()
        assert store.plans_dir.is_absolute()
        assert store.plans_dir.parts[-2:] == ("jetsam", "plans")
        assert store.plans_dir != Path(".jetsam") / "plans"

    def test_xdg_state_home_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """With XDG_STATE_HOME unset, the location falls back to
        ~/.local/state/jetsam/plans (absolute)."""
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        loc = default_plans_dir()
        assert loc.is_absolute()
        assert loc.parts[-4:] == (".local", "state", "jetsam", "plans")


class TestPlanIdValidation:
    @pytest.mark.parametrize("bad_id", ["../etc/passwd", "p_XYZ", "; rm", "p_",
                                        "p_dead/beef", "", "p_dead\n"])
    def test_load_rejects_invalid_ids(self, bad_id: str):
        store = PlanStore()
        assert store.load(bad_id) is None

    @pytest.mark.parametrize("bad_id", ["../etc/passwd", "p_XYZ", "; rm"])
    def test_delete_is_noop_for_invalid_ids(self, bad_id: str, tmp_path: Path):
        store = PlanStore()
        # Also make sure a traversal target that exists is not touched.
        victim = tmp_path / "victim"
        victim.write_text("keep me")
        store.delete(str(victim))  # not a valid plan id -> no-op
        assert victim.exists()
        store.delete(bad_id)  # must not raise / escape

    def test_save_raises_on_invalid_id(self):
        store = PlanStore()
        plan = _make_plan("p_notHEX", repo_root="/tmp")
        with pytest.raises(ValueError):
            store.save(plan)

    def test_generated_ids_are_valid(self):
        store = PlanStore()
        plan_id = generate_plan_id()
        plan = _make_plan(plan_id, repo_root="/tmp")
        store.save(plan)  # must not raise
        assert store.load(plan_id) is not None
