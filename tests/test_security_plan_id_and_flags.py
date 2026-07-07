"""Security regression tests for GHSA-w893-5jfc-rwq9.

Two MCP-reachable issues:

1. ``cancel(id)`` -> ``PlanStore.delete`` joined an unvalidated id into a path
   and ``unlink``ed it, so an absolute or ``../`` id escaped the plans dir and
   deleted arbitrary files. **This half was fixed in v1.1.5** (PlanStore now
   validates ``^p_[0-9a-f]+$`` in save/load/delete). The tests below lock that
   in against future refactors; the traversal repros always target a
   test-created temp sentinel, never a real user file.

2. ``strategy`` (finish) and ``event`` (pr_review) were interpolated as
   ``f"--{...}"`` into a ``gh`` argv on the MCP path with **no allowlist** (the
   CLI constrained them via ``click.Choice``; the MCP path did not), so
   ``strategy="admin"`` produced ``gh pr merge --admin``. That half is fixed
   here — those tests are red on v1.1.5 and green after the change.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jetsam.core.planner import plan_finish
from jetsam.core.plans import PlanStore, generate_plan_id
from jetsam.core.state import PRInfo, RepoState
from jetsam.platforms.github import GitHubPlatform

# --------------------------------------------------------------------------- #
# 1. Plan-id path safety (regression lock-in for the v1.1.5 fix)
# --------------------------------------------------------------------------- #


def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlanStore:
    # PlanStore() resolves plans_dir from XDG_STATE_HOME; point it at a tmp dir
    # so the traversal sentinels below sit just outside plans_dir.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return PlanStore()  # plans_dir == tmp_path/jetsam/plans


def test_delete_rejects_absolute_id_and_does_not_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute id must not escape plans_dir and delete an outside file."""
    sentinel = tmp_path / "abs_victim.json"
    sentinel.write_text("important user data")

    store = _store(tmp_path, monkeypatch)
    # id is an absolute path (minus the .json suffix the store appends).
    store.delete(str(tmp_path / "abs_victim"))

    assert sentinel.exists(), "absolute-path id escaped plans_dir and deleted a file"


def test_delete_rejects_dotdot_id_and_does_not_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``../`` traversal id must not delete a file outside plans_dir."""
    sentinel = tmp_path / "dotdot_victim.json"
    sentinel.write_text("important user data")

    store = _store(tmp_path, monkeypatch)  # plans_dir == tmp_path/jetsam/plans
    # plans_dir/../../dotdot_victim.json resolves up to tmp_path/dotdot_victim.json
    store.delete("../../dotdot_victim")

    assert sentinel.exists(), "'../' id escaped plans_dir and deleted a file"


def test_delete_valid_id_cancels_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive path: a well-formed id still cancels (deletes its own plan file)."""
    store = _store(tmp_path, monkeypatch)
    plan_file = store.plans_dir / "p_deadbeef.json"
    plan_file.write_text("{}")

    store.delete("p_deadbeef")

    assert not plan_file.exists(), "valid id did not cancel its own plan"


def test_load_rejects_invalid_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load() must refuse a malformed id rather than touching an outside path."""
    store = _store(tmp_path, monkeypatch)
    assert store.load("../../etc/passwd") is None
    assert store.load(str(tmp_path / "anything")) is None


def test_save_rejects_invalid_plan_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """save() must reject a plan whose id is not path-safe."""
    from jetsam.core.planner import Plan

    store = _store(tmp_path, monkeypatch)
    bad = Plan(plan_id="../evil", verb="save", steps=[], state_hash="x", repo_root=str(tmp_path))
    with pytest.raises(ValueError):
        store.save(bad)


def test_generated_ids_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids from generate_plan_id() must always validate (no false negatives)."""
    from jetsam.core.planner import Plan

    store = _store(tmp_path, monkeypatch)
    pid = generate_plan_id()
    store.save(Plan(plan_id=pid, verb="save", steps=[], state_hash="x", repo_root=str(tmp_path)))
    assert (store.plans_dir / f"{pid}.json").exists()


# --------------------------------------------------------------------------- #
# 2. gh flag allowlisting: strategy (finish) + event (pr_review) — fixed here
# --------------------------------------------------------------------------- #


def _finish_state() -> RepoState:
    return RepoState(
        branch="feature",
        upstream="origin/feature",
        default_branch="main",
        dirty=False,
        staged=[],
        unstaged=[],
        untracked=[],
        ahead=1,
        behind=0,
        stash_count=0,
        platform="github",
        remote="user/repo",
        remote_url="git@github.com:user/repo.git",
        head_sha="abc123",
        repo_root="/tmp/repo",
        pr=PRInfo(number=42, state="open", title="feature"),
    )


def test_plan_finish_rejects_injected_strategy() -> None:
    """finish(strategy="admin") must be rejected at plan-build time (fail fast)."""
    from jetsam.config.manager import JetsamConfig

    with pytest.raises(ValueError):
        plan_finish(_finish_state(), plan_id="p_test", strategy="admin", config=JetsamConfig())


def test_plan_finish_accepts_valid_strategies() -> None:
    """The allowlisted strategies still plan normally."""
    from jetsam.config.manager import JetsamConfig

    for strat in ("squash", "merge", "rebase"):
        plan = plan_finish(
            _finish_state(), plan_id="p_test", strategy=strat, config=JetsamConfig()
        )
        merge = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge.params["strategy"] == strat


def test_pr_merge_rejects_injected_strategy_before_gh() -> None:
    """platform.pr_merge must reject a non-allowlisted strategy before any gh call."""
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh") as run_gh:
        run_gh.return_value = (True, "", "")
        with pytest.raises(ValueError):
            platform.pr_merge(1, strategy="admin")
        run_gh.assert_not_called()


def test_pr_merge_valid_strategy_invokes_gh() -> None:
    """Positive path: an allowlisted strategy reaches gh with the right flag."""
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh", MagicMock(return_value=(True, "", ""))) as run_gh:
        assert platform.pr_merge(1, strategy="squash", delete_branch=False) is True
        args = run_gh.call_args.args[0]
        assert "--squash" in args
        assert "--admin" not in args


def test_pr_review_rejects_injected_event_before_gh() -> None:
    """platform.pr_review must reject a non-allowlisted event before any gh call."""
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh") as run_gh:
        run_gh.return_value = (True, "", "")
        with pytest.raises(ValueError):
            platform.pr_review(1, body="x", event="admin")
        run_gh.assert_not_called()


def test_pr_review_valid_event_invokes_gh() -> None:
    """Positive path: an allowlisted review event reaches gh."""
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh", MagicMock(return_value=(True, "ok", ""))) as run_gh:
        platform.pr_review(1, body="looks good", event="approve")
        args = run_gh.call_args.args[0]
        assert "--approve" in args
