"""Submodule alternates guard for tidy and finish (CQO-D2).

A submodule store in one worktree can borrow objects from a submodule store
in another worktree through ``objects/info/alternates`` (for example after
``git submodule update --reference <other tree>``). The lender store lives in
``<common>/worktrees/<name>/modules/``. ``git worktree prune`` deletes that
directory for a worktree whose folder is gone, and the borrower then fails
with "unable to normalize alternate object path".

The plan must name each borrowing file before confirm(), and refuse in its
first step unless the caller asks for the repoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from jetsam.core.executor import execute_plan
from jetsam.core.planner import plan_finish, plan_tidy
from jetsam.core.state import build_state


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "protocol.file.allow=always", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout


def _fsck_ok(path: Path) -> bool:
    r = subprocess.run(
        ["git", "fsck", "--connectivity-only", "--no-dangling"],
        cwd=path, capture_output=True, text=True,
    )
    return r.returncode == 0


@pytest.fixture
def borrowing_trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """repo + tree A with its own sub store + tree B whose sub borrows from A."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for k in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(k, "Test")
    for k in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "test@test.com")

    src = tmp_path / "src"
    _git("init", "-q", "-b", "main", str(src), cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "sub", cwd=src)

    repo = tmp_path / "repo"
    _git("init", "-q", "-b", "main", str(repo), cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    # file:// forces a real fetch: a plain local path would copy objects.
    _git("submodule", "add", "-q", f"file://{src}", "sub", cwd=repo)
    _git("commit", "-q", "-m", "add sub", cwd=repo)
    _git("clone", "-q", "--bare", str(repo), str(tmp_path / "origin.git"), cwd=tmp_path)
    _git("remote", "add", "origin", str(tmp_path / "origin.git"), cwd=repo)

    a = tmp_path / "a"
    b = tmp_path / "b"
    _git("worktree", "add", "-q", "-b", "a", str(a), cwd=repo)
    _git("submodule", "update", "-q", "--init", cwd=a)
    _git("worktree", "add", "-q", "-b", "b", str(b), cwd=repo)
    _git("submodule", "update", "-q", "--init", "--reference", str(a / "sub"), cwd=b)

    b_alt = repo / ".git/worktrees/b/modules/sub/objects/info/alternates"
    assert "worktrees/a/modules/sub/objects" in b_alt.read_text()  # precondition
    return {"repo": repo, "a": a, "b": b, "b_alt": b_alt,
            "a_gitdir": repo / ".git/worktrees/a"}


# --- tidy: the measured hazard ------------------------------------------


def test_tidy_refuses_in_plan_when_a_stale_tree_lends_objects(borrowing_trees):
    t = borrowing_trees
    shutil.rmtree(t["a"])  # folder gone: `git worktree prune` would drop its gitdir

    plan = plan_tidy(build_state(cwd=str(t["b"])), plan_id="p_1")

    # Visible before confirm(): first step refuses, warnings name the file.
    assert plan.steps[0].action == "alternates_refuse"
    assert any(str(t["b_alt"]) in w for w in plan.warnings)

    result = execute_plan(plan, cwd=str(t["b"]))
    assert result.results[0].ok is False
    assert str(t["b_alt"]) in (result.results[0].error or "")
    assert len(result.results) == 1  # nothing after the refusal ran
    assert (t["a_gitdir"] / "modules/sub").is_dir()
    assert _fsck_ok(t["b"] / "sub")


def test_tidy_repoint_alternates_prunes_and_borrower_still_works(borrowing_trees):
    t = borrowing_trees
    shutil.rmtree(t["a"])

    plan = plan_tidy(build_state(cwd=str(t["b"])), plan_id="p_1",
                     repoint_alternates=True)
    assert plan.steps[0].action == "alternates_repoint"

    result = execute_plan(plan, cwd=str(t["b"]))
    assert result.status == "ok", result.results
    assert not t["a_gitdir"].exists()
    assert "worktrees/a/" not in t["b_alt"].read_text()
    assert _fsck_ok(t["b"] / "sub")


def test_tidy_without_borrowers_plans_as_before(borrowing_trees):
    t = borrowing_trees
    # B borrows from A; nothing borrows from B. Pruning B is safe.
    shutil.rmtree(t["b"])

    plan = plan_tidy(build_state(cwd=str(t["a"])), plan_id="p_1")
    assert [s.action for s in plan.steps] == [
        "remote_prune", "prune_merged_branches", "worktree_prune",
    ]
    result = execute_plan(plan, cwd=str(t["a"]))
    assert result.status == "ok", result.results
    assert not (t["repo"] / ".git/worktrees/b").exists()


# --- finish: plan-time backstop -----------------------------------------
# Measured on a7f41ff with git 2.43: finish's `git worktree remove` (no
# --force) refuses any tree with submodules, so finish cannot break B today.
# The check makes the plan name the borrower before confirm(), and before
# pr_merge, in case the remove ever gains --force.


def test_finish_plan_names_borrower_before_any_step(borrowing_trees):
    t = borrowing_trees
    state = build_state(cwd=str(t["a"]))

    plan = plan_finish(state, plan_id="p_1", worktree_path=str(t["a"]))

    assert plan.steps[0].action == "alternates_refuse"
    assert any(str(t["b_alt"]) in w for w in plan.warnings)
    result = execute_plan(plan, cwd=str(t["a"]))
    assert len(result.results) == 1 and result.results[0].ok is False
    assert t["a"].is_dir()


def test_finish_repoint_alternates_repoints_first(borrowing_trees):
    t = borrowing_trees
    state = build_state(cwd=str(t["a"]))

    plan = plan_finish(state, plan_id="p_1", worktree_path=str(t["a"]),
                       repoint_alternates=True)

    assert plan.steps[0].action == "alternates_repoint"
    execute_plan(plan, cwd=str(t["a"]))
    assert "worktrees/a/" not in t["b_alt"].read_text()
    assert _fsck_ok(t["b"] / "sub")
