"""Phase 3 integration tests: start, finish, tidy, issues, prs, completions."""

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from jetsam.cli.main import cli
from jetsam.core.planner import (
    _slugify,
    plan_finish,
    plan_start,
    plan_tidy,
)
from jetsam.core.state import PRInfo, RepoState, WorktreeInfo
from jetsam.platforms import get_platform
from jetsam.platforms.base import IssueDetails


def _make_state(**kwargs):
    defaults = dict(
        branch="feature",
        upstream="origin/feature",
        default_branch="main",
        dirty=True,
        staged=["already_staged.py"],
        unstaged=["modified.py", "other.py"],
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


# --- Slugify ---


class TestSlugify:
    def test_basic(self):
        assert _slugify("Fix parser bug") == "fix-parser-bug"

    def test_special_chars(self):
        assert _slugify("Add  feature!! (important)") == "add-feature-important"

    def test_max_length(self):
        long_title = "a very long title that should be truncated at word boundary"
        slug = _slugify(long_title, max_length=20)
        assert len(slug) <= 20
        assert not slug.endswith("-")

    def test_empty(self):
        assert _slugify("") == ""

    def test_numbers(self):
        assert _slugify("Issue 42: fix it") == "issue-42-fix-it"

    def test_dashes_preserved(self):
        assert _slugify("already-a-slug") == "already-a-slug"

    def test_leading_trailing_stripped(self):
        assert _slugify("--hello--") == "hello"


# --- Plan Start ---


class TestPlanStart:
    def test_branch_name_from_target(self):
        state = _make_state(dirty=False)
        plan = plan_start(state, plan_id="p_test", target="fix-parser")
        assert plan.verb == "start"
        assert plan.params["branch"] == "fix-parser"
        actions = [s.action for s in plan.steps]
        assert "checkout" in actions

    def test_issue_number_with_title(self):
        state = _make_state(dirty=False)
        plan = plan_start(
            state, plan_id="p_test",
            target="42",
            issue_title="Fix parser bug",
        )
        assert plan.params["branch"] == "42-fix-parser-bug"

    def test_issue_number_without_title(self):
        state = _make_state(dirty=False)
        plan = plan_start(state, plan_id="p_test", target="42")
        assert plan.params["branch"] == "issue-42"

    def test_branch_prefix(self):
        state = _make_state(dirty=False)
        plan = plan_start(
            state, plan_id="p_test",
            target="fix-it",
            branch_prefix="feature/",
        )
        assert plan.params["branch"] == "feature/fix-it"

    def test_prefix_not_doubled(self):
        state = _make_state(dirty=False)
        plan = plan_start(
            state, plan_id="p_test",
            target="feature/fix-it",
            branch_prefix="feature/",
        )
        assert plan.params["branch"] == "feature/fix-it"

    def test_dirty_stashes(self):
        state = _make_state(dirty=True)
        plan = plan_start(state, plan_id="p_test", target="new-feature")
        actions = [s.action for s in plan.steps]
        assert actions[0] == "stash"
        assert actions[-1] == "stash_pop"
        assert any("stash" in w.lower() for w in plan.warnings)

    def test_worktree_mode(self):
        state = _make_state(dirty=False)
        plan = plan_start(
            state, plan_id="p_test",
            target="wt-feature",
            worktree=True,
        )
        actions = [s.action for s in plan.steps]
        assert "worktree_add" in actions
        assert "checkout" not in actions
        assert "stash" not in actions

    def test_custom_base(self):
        state = _make_state(dirty=False)
        plan = plan_start(
            state, plan_id="p_test",
            target="hotfix",
            base="release/v2",
        )
        assert plan.params["base"] == "release/v2"

    def test_checkout_includes_start_point(self):
        state = _make_state(dirty=False)
        plan = plan_start(state, plan_id="p_test", target="feat")
        checkout = next(s for s in plan.steps if s.action == "checkout")
        assert checkout.params["create"] is True
        assert checkout.params["start_point"] == "main"


# --- Plan Finish ---


class TestPlanFinish:
    def test_with_pr(self):
        pr = PRInfo(number=42, state="open", title="Fix bug")
        state = _make_state(pr=pr, dirty=False)
        plan = plan_finish(state, plan_id="p_test")
        assert plan.verb == "finish"
        actions = [s.action for s in plan.steps]
        assert "pr_merge" in actions
        assert "checkout" in actions
        assert "fetch" in actions

    def test_pr_merge_has_number(self):
        pr = PRInfo(number=42, state="open", title="Fix bug")
        state = _make_state(pr=pr, dirty=False)
        plan = plan_finish(state, plan_id="p_test")
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["number"] == 42
        assert merge_step.params["strategy"] == "squash"

    def test_no_pr(self):
        state = _make_state(pr=None, dirty=False)
        plan = plan_finish(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "pr_merge" not in actions
        assert "checkout" in actions

    def test_already_on_default(self):
        state = _make_state(branch="main", default_branch="main", dirty=False)
        plan = plan_finish(state, plan_id="p_test")
        assert len(plan.steps) == 0
        assert any("default branch" in w.lower() for w in plan.warnings)

    def test_no_delete_flag(self):
        pr = PRInfo(number=42, state="open", title="Fix bug")
        state = _make_state(pr=pr, dirty=False)
        plan = plan_finish(state, plan_id="p_test", no_delete=True)
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["delete_branch"] is False
        actions = [s.action for s in plan.steps]
        assert "branch_delete" not in actions

    def test_dirty_warning(self):
        state = _make_state(dirty=True)
        plan = plan_finish(state, plan_id="p_test")
        assert any("uncommitted" in w.lower() for w in plan.warnings)

    def test_merge_strategy(self):
        pr = PRInfo(number=10, state="open")
        state = _make_state(pr=pr, dirty=False)
        plan = plan_finish(state, plan_id="p_test", strategy="rebase")
        merge_step = next(s for s in plan.steps if s.action == "pr_merge")
        assert merge_step.params["strategy"] == "rebase"

    def test_worktree_mode(self):
        pr = PRInfo(number=42, state="open")
        state = _make_state(pr=pr, dirty=False)
        plan = plan_finish(
            state, plan_id="p_test",
            worktree_path="/tmp/wt/feature",
        )
        actions = [s.action for s in plan.steps]
        assert "worktree_remove" in actions
        assert "checkout" not in actions  # worktree_remove replaces checkout


# --- Plan Tidy ---


class TestPlanTidy:
    def test_basic(self):
        state = _make_state(dirty=False)
        plan = plan_tidy(state, plan_id="p_test")
        assert plan.verb == "tidy"
        actions = [s.action for s in plan.steps]
        assert "remote_prune" in actions
        assert "prune_merged_branches" in actions

    def test_no_worktree_prune_without_worktree(self):
        state = _make_state(dirty=False)
        plan = plan_tidy(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "worktree_prune" not in actions

    def test_worktree_prune_when_worktrees_active(self):
        wt = WorktreeInfo(active=False, root="/tmp/repo", current="/tmp/repo")
        state = _make_state(dirty=False, worktree=wt)
        plan = plan_tidy(state, plan_id="p_test")
        actions = [s.action for s in plan.steps]
        assert "worktree_prune" in actions


# --- Platform Factory ---


class TestGetPlatform:
    def test_github(self):
        platform = get_platform("github", cwd="/tmp")
        from jetsam.platforms.github import GitHubPlatform
        assert isinstance(platform, GitHubPlatform)

    def test_gitlab(self):
        platform = get_platform("gitlab", cwd="/tmp")
        from jetsam.platforms.gitlab import GitLabPlatform
        assert isinstance(platform, GitLabPlatform)

    def test_unknown(self):
        platform = get_platform("unknown")
        assert platform is None

    def test_empty(self):
        platform = get_platform("")
        assert platform is None


# --- GitHub Issue Parsing ---


class TestGitHubIssueParsing:
    def test_parse_issue(self):
        from jetsam.platforms.github import _parse_issue
        data = {
            "number": 42,
            "title": "Fix parser",
            "state": "OPEN",
            "body": "Details",
            "url": "https://github.com/user/repo/issues/42",
            "labels": [{"name": "bug"}, {"name": "p1"}],
            "assignees": [{"login": "dev1"}],
        }
        issue = _parse_issue(data)
        assert issue.number == 42
        assert issue.title == "Fix parser"
        assert issue.state == "open"
        assert issue.labels == ["bug", "p1"]
        assert issue.assignees == ["dev1"]

    def test_parse_issue_missing_fields(self):
        from jetsam.platforms.github import _parse_issue
        data = {"number": 1, "state": "OPEN"}
        issue = _parse_issue(data)
        assert issue.number == 1
        assert issue.title == ""
        assert issue.labels == []
        assert issue.assignees == []


# --- CLI Verbs ---


class TestStartCLI:
    def test_dry_run(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["start", "new-feature", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "new-feature" in result.output

    def test_dry_run_json(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "start", "new-feature", "--dry-run"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["verb"] == "start"

    def test_execute(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["start", "test-branch", "--execute"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0

        # Verify branch was created
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=tmp_git_repo, capture_output=True, text=True,
        )
        assert branch_result.stdout.strip() == "test-branch"

    def test_alias_b(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["b", "alias-test", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "alias-test" in result.output


class TestFinishCLI:
    def test_dry_run(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        # First create a feature branch
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"],
            cwd=tmp_git_repo, check=True, env=env, capture_output=True,
        )
        result = runner.invoke(cli, ["finish", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0

    def test_on_default_branch(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["finish", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "default branch" in result.output.lower()

    def test_alias_f(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["f", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0


class TestTidyCLI:
    def test_dry_run(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["tidy", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "prune" in result.output.lower() or "Prune" in result.output

    def test_dry_run_json(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "tidy", "--dry-run"],
                               catch_exceptions=False)
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["verb"] == "tidy"

    def test_alias_t(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["t", "--dry-run"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0


class TestCompletionsCLI:
    def test_bash_completions(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["completions", "bash"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0
        assert "jetsam" in result.output.lower() or "JETSAM" in result.output

    def test_zsh_completions(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["completions", "zsh"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0

    def test_fish_completions(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["completions", "fish"], obj={"json": False},
                               catch_exceptions=False)
        assert result.exit_code == 0


# --- Issue Details Dataclass ---


class TestIssueDetails:
    def test_create(self):
        issue = IssueDetails(
            number=42,
            title="Test issue",
            state="open",
        )
        assert issue.number == 42
        assert issue.title == "Test issue"
        assert issue.labels == []
        assert issue.assignees == []

    def test_with_all_fields(self):
        issue = IssueDetails(
            number=1,
            title="Full issue",
            state="closed",
            body="Description",
            url="https://example.com",
            labels=["bug"],
            assignees=["user1"],
        )
        assert issue.state == "closed"
        assert issue.labels == ["bug"]
