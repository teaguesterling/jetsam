"""Regression tests for the remaining items of issue #19.

1. Follow-up allowlist audit: fixed-value-set params that reach a gh/glab/git
   argv (``pr_list``/``issues`` state filters, ``issue_close`` reason, sync
   strategy) are validated on the MCP path — rejected with the standard
   ``{error, message, recoverable}`` dict before anything reaches subprocess
   argv — and again at the platform boundary. Free-form params (titles,
   bodies, branch names) are deliberately NOT restricted.

2. Truthful stash warnings: ``plan_switch``/``plan_start`` no longer claim
   "changes will be stashed" when the only dirt is untracked files, which
   ``git stash push`` (no ``-u``) does not capture. Untracked-only trees plan
   no stash steps and get an informational note instead.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jetsam.core.planner import plan_start, plan_switch, plan_sync
from jetsam.core.state import RepoState
from jetsam.platforms.github import GitHubPlatform
from jetsam.platforms.gitlab import GitLabPlatform


def _make_state(**kwargs) -> RepoState:
    defaults = dict(
        branch="feature",
        upstream="origin/feature",
        default_branch="main",
        dirty=True,
        staged=["already_staged.py"],
        unstaged=["modified.py"],
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


# --------------------------------------------------------------------------- #
# 1a. Platform boundary: state filters / close reason / merge strategy
# --------------------------------------------------------------------------- #


def test_github_pr_list_rejects_invalid_state_before_gh() -> None:
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh") as run_gh:
        with pytest.raises(ValueError):
            platform.pr_list(state="--author=evil")
        run_gh.assert_not_called()


def test_github_pr_list_valid_states_invoke_gh() -> None:
    platform = GitHubPlatform()
    for state in ("open", "closed", "merged", "all"):
        with patch.object(platform, "_run_gh", MagicMock(return_value=(True, "[]", ""))) as run_gh:
            platform.pr_list(state=state)
            args = run_gh.call_args.args[0]
            assert args[args.index("--state") + 1] == state


def test_github_issue_list_rejects_invalid_state_before_gh() -> None:
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh") as run_gh:
        with pytest.raises(ValueError):
            platform.issue_list(state="--web")
        run_gh.assert_not_called()


def test_github_issue_close_rejects_invalid_reason_before_gh() -> None:
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh") as run_gh:
        with pytest.raises(ValueError):
            platform.issue_close(1, reason="--undo")
        run_gh.assert_not_called()


def test_github_issue_close_normalizes_hyphenated_reason() -> None:
    """The documented "not-planned" spelling reaches gh as "not planned"."""
    platform = GitHubPlatform()
    with patch.object(platform, "_run_gh", MagicMock(return_value=(True, "", ""))) as run_gh:
        platform.issue_close(1, reason="not-planned")
        args = run_gh.call_args.args[0]
        assert args[args.index("--reason") + 1] == "not planned"


def test_gitlab_pr_list_rejects_invalid_state_before_glab() -> None:
    platform = GitLabPlatform()
    with patch.object(platform, "_run_glab") as run_glab:
        with pytest.raises(ValueError):
            platform.pr_list(state="--web")
        run_glab.assert_not_called()


def test_gitlab_issue_list_rejects_invalid_state_before_glab() -> None:
    platform = GitLabPlatform()
    with patch.object(platform, "_run_glab") as run_glab:
        with pytest.raises(ValueError):
            platform.issue_list(state="--web")
        run_glab.assert_not_called()


def test_gitlab_pr_merge_rejects_invalid_strategy_before_glab() -> None:
    platform = GitLabPlatform()
    with patch.object(platform, "_run_glab") as run_glab:
        with pytest.raises(ValueError):
            platform.pr_merge(1, strategy="admin")
        run_glab.assert_not_called()


# --------------------------------------------------------------------------- #
# 1b. plan_sync strategy allowlist (was silently coerced to "merge")
# --------------------------------------------------------------------------- #


def test_plan_sync_rejects_invalid_strategy() -> None:
    with pytest.raises(ValueError):
        plan_sync(_make_state(dirty=False), plan_id="p_test", strategy="theirs")


def test_plan_sync_accepts_valid_strategies() -> None:
    for strategy in ("rebase", "merge"):
        plan = plan_sync(_make_state(dirty=False), plan_id="p_test", strategy=strategy)
        actions = [s.action for s in plan.steps]
        assert strategy in actions


def test_plan_sync_default_strategy_still_allowed() -> None:
    plan = plan_sync(_make_state(dirty=False), plan_id="p_test", strategy=None)
    assert plan.verb == "sync"


# --------------------------------------------------------------------------- #
# 1c. MCP tool layer: invalid values return the standard error dict
# --------------------------------------------------------------------------- #


def _mcp_tool(name: str):
    from mcp.server.fastmcp import FastMCP

    from jetsam.mcp import tools as mcp_tools

    mcp = FastMCP("test")
    mcp_tools.register_tools(mcp)
    return mcp._tool_manager._tools[name].fn


def _assert_invalid_argument(result) -> None:
    assert isinstance(result, dict)
    assert result["error"] == "invalid_argument"
    assert "message" in result
    assert result["recoverable"] is True


def test_mcp_pr_list_rejects_invalid_state() -> None:
    _assert_invalid_argument(_mcp_tool("pr_list")(state="--web"))


def test_mcp_issues_rejects_invalid_state() -> None:
    _assert_invalid_argument(_mcp_tool("issues")(state="merged"))


def test_mcp_issue_close_rejects_invalid_reason() -> None:
    _assert_invalid_argument(_mcp_tool("issue_close")(number=1, reason="--undo"))


def test_mcp_pr_review_rejects_invalid_event() -> None:
    _assert_invalid_argument(_mcp_tool("pr_review")(event="--admin", body="x"))


def test_mcp_sync_rejects_invalid_strategy() -> None:
    _assert_invalid_argument(_mcp_tool("sync")(strategy="theirs"))


def test_mcp_finish_invalid_strategy_returns_error_dict(
    tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_DIR", str(tmp_git_repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_git_repo))
    _assert_invalid_argument(_mcp_tool("finish")(strategy="admin"))


# --------------------------------------------------------------------------- #
# 2. Truthful stash warnings (plan_switch / plan_start)
# --------------------------------------------------------------------------- #


def test_switch_untracked_only_plans_no_stash_and_does_not_claim_one() -> None:
    state = _make_state(dirty=True, staged=[], unstaged=[], untracked=["scratch.txt"])
    plan = plan_switch(state, plan_id="p_test", branch="other")
    actions = [s.action for s in plan.steps]
    assert actions == ["checkout"], "untracked-only dirt must not plan a stash"
    assert not any("will be stashed" in w for w in plan.warnings)
    assert any("not stashed" in w.lower() for w in plan.warnings)


def test_switch_tracked_dirty_still_stashes_with_truthful_warning() -> None:
    state = _make_state(dirty=True)
    plan = plan_switch(state, plan_id="p_test", branch="other")
    actions = [s.action for s in plan.steps]
    assert actions == ["stash", "checkout", "stash_pop"]
    assert any("Tracked changes will be stashed" in w for w in plan.warnings)


def test_switch_clean_tree_no_warning() -> None:
    state = _make_state(dirty=False, staged=[], unstaged=[], untracked=[])
    plan = plan_switch(state, plan_id="p_test", branch="other")
    assert [s.action for s in plan.steps] == ["checkout"]
    assert plan.warnings == []


def test_start_untracked_only_plans_no_stash_and_does_not_claim_one() -> None:
    state = _make_state(dirty=True, staged=[], unstaged=[], untracked=["scratch.txt"])
    plan = plan_start(state, plan_id="p_test", target="new-feature", worktree=False)
    actions = [s.action for s in plan.steps]
    assert "stash" not in actions
    assert "stash_pop" not in actions
    assert not any("will be stashed" in w for w in plan.warnings)
    assert any("not stashed" in w.lower() for w in plan.warnings)


def test_start_tracked_dirty_still_stashes_with_truthful_warning() -> None:
    state = _make_state(dirty=True)
    plan = plan_start(state, plan_id="p_test", target="new-feature", worktree=False)
    actions = [s.action for s in plan.steps]
    assert actions[0] == "stash"
    assert actions[-1] == "stash_pop"
    assert any("Tracked changes will be stashed" in w for w in plan.warnings)
