"""Regression tests for issue #19.

`_exec_commit` committed with `git commit -m <msg>` and no pathspec, so it
committed the *entire* index rather than the plan's file list. Because
`modify_plan(exclude=...)` only filters the *stage* step, an excluded (or
otherwise unrelated already-staged) file still landed in the commit — a false
assurance. The commit step now carries an explicit file list and commits only
that pathspec; `modify_plan(exclude=...)` filters it too.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from jetsam.core.executor import _exec_commit
from jetsam.core.planner import Plan, PlanStep, plan_save
from jetsam.core.plans import update_plan
from jetsam.core.state import build_state

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=_ENV, capture_output=True, text=True, check=True
    ).stdout


def _committed_files(repo: Path) -> set[str]:
    out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    return {line for line in out.splitlines() if line}


def _staged_files(repo: Path) -> set[str]:
    out = _git(repo, "diff", "--cached", "--name-only")
    return {line for line in out.splitlines() if line}


def test_exec_commit_commits_only_pathspec_not_whole_index(tmp_git_repo: Path) -> None:
    """A commit step with an explicit file list must not sweep in an unrelated
    already-staged file."""
    repo = tmp_git_repo

    # Two tracked files, both modified and staged (a dirty index with an
    # unrelated staged change alongside the plan's own file).
    (repo / "wanted.py").write_text("wanted = 1\n")
    (repo / "unrelated.py").write_text("unrelated = 1\n")
    _git(repo, "add", "wanted.py", "unrelated.py")

    step = PlanStep(action="commit", params={"message": "only wanted", "files": ["wanted.py"]})
    result = _exec_commit(step, cwd=str(repo))
    assert result.ok, result.error

    committed = _committed_files(repo)
    assert "wanted.py" in committed
    assert "unrelated.py" not in committed, "commit swept in an unrelated staged file"
    # The unrelated change is left untouched in the index.
    assert "unrelated.py" in _staged_files(repo)


def test_plan_save_populates_commit_file_list(tmp_git_repo: Path) -> None:
    """plan_save must give the commit step an explicit file list (the pathspec)."""
    repo = tmp_git_repo
    (repo / "a.py").write_text("a = 1\n")
    (repo / "b.py").write_text("b = 1\n")

    state = build_state(cwd=str(repo))
    plan = plan_save(state, plan_id="p_deadbeef", message="add", files=["a.py", "b.py"])
    commit = next(s for s in plan.steps if s.action == "commit")
    assert set(commit.params.get("files", [])) == {"a.py", "b.py"}


def test_modify_plan_exclude_filters_commit_pathspec() -> None:
    """modify_plan(exclude=...) must filter the commit file list, not only stage."""
    plan = Plan(
        plan_id="p_deadbeef",
        verb="save",
        steps=[
            PlanStep(action="stage", params={"files": ["a.py", "b_generated.py"]}),
            PlanStep(
                action="commit",
                params={"message": "m", "file_count": 2, "files": ["a.py", "b_generated.py"]},
            ),
        ],
        state_hash="x",
        repo_root="/tmp/repo",
    )

    update_plan(plan, exclude="*generated*")

    commit = next(s for s in plan.steps if s.action == "commit")
    assert commit.params["files"] == ["a.py"], "exclude did not filter the commit pathspec"


def test_runtime_config_has_no_dead_auto_confirm_field() -> None:
    """The unused auto_confirm_safe_verbs config knob is removed."""
    from jetsam.config.runtime import JetsamRuntimeConfig

    assert not hasattr(JetsamRuntimeConfig(), "auto_confirm_safe_verbs")
