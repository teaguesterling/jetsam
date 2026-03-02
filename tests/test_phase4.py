"""Phase 4 tests: release verb, init --aliases, worktree shared paths, error recovery."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from jetsam.cli.main import cli
from jetsam.cli.verbs.init import (
    ALIAS_MARKER,
    generate_alias_block_fish,
    generate_alias_block_posix,
    has_alias_marker,
)
from jetsam.core.executor import _suggest_recovery, execute_plan
from jetsam.core.planner import plan_release
from jetsam.core.state import RepoState
from jetsam.worktree.integration import setup_shared_paths


def _make_state(**kwargs):
    defaults = dict(
        branch="main",
        upstream="origin/main",
        default_branch="main",
        dirty=False,
        staged=[],
        unstaged=[],
        untracked=[],
        ahead=0,
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


# --- Plan Release ---


class TestPlanRelease:
    def test_basic_plan(self, tmp_git_repo: Path):
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")
        assert plan.verb == "release"
        actions = [s.action for s in plan.steps]
        assert actions == ["tag_create", "push_tag", "release_create"]
        assert plan.params["tag"] == "v0.1.0"
        assert plan.params["title"] == "v0.1.0"  # defaults to tag

    def test_custom_title(self, tmp_git_repo: Path):
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(
            state, plan_id="p_test",
            tag="v0.2.0", title="Version 0.2.0",
        )
        assert plan.params["title"] == "Version 0.2.0"
        release_step = next(s for s in plan.steps if s.action == "release_create")
        assert release_step.params["title"] == "Version 0.2.0"

    def test_draft_flag(self, tmp_git_repo: Path):
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(
            state, plan_id="p_test",
            tag="v0.1.0-rc1", draft=True,
        )
        release_step = next(s for s in plan.steps if s.action == "release_create")
        assert release_step.params["draft"] is True

    def test_notes(self, tmp_git_repo: Path):
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(
            state, plan_id="p_test",
            tag="v0.1.0", notes="First release!",
        )
        release_step = next(s for s in plan.steps if s.action == "release_create")
        assert release_step.params["notes"] == "First release!"

    def test_dirty_warning(self, tmp_git_repo: Path):
        state = _make_state(dirty=True, repo_root=str(tmp_git_repo))
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")
        assert any("uncommitted" in w.lower() for w in plan.warnings)

    def test_not_on_default_branch_warning(self, tmp_git_repo: Path):
        state = _make_state(branch="feature", repo_root=str(tmp_git_repo))
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")
        assert any("default branch" in w.lower() for w in plan.warnings)

    def test_existing_tag_warning(self, tmp_git_repo: Path):
        """When the tag already exists, skip tag_create and warn."""
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }
        subprocess.run(
            ["git", "tag", "-a", "v0.1.0", "-m", "existing"],
            cwd=tmp_git_repo, check=True, env=env, capture_output=True,
        )
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")
        assert any("already exists" in w for w in plan.warnings)
        actions = [s.action for s in plan.steps]
        assert "tag_create" not in actions
        assert "push_tag" in actions
        assert "release_create" in actions

    def test_tag_create_params(self, tmp_git_repo: Path):
        state = _make_state(repo_root=str(tmp_git_repo))
        plan = plan_release(
            state, plan_id="p_test",
            tag="v1.0.0", title="Version 1.0",
        )
        tag_step = next(s for s in plan.steps if s.action == "tag_create")
        assert tag_step.params["tag"] == "v1.0.0"
        assert tag_step.params["message"] == "Version 1.0"


# --- Release Executor ---


class TestReleaseExecutor:
    def test_tag_create_step(self, tmp_git_repo: Path):
        """Test tag_create executor against real repo."""
        from jetsam.core.state import build_state

        cwd = str(tmp_git_repo)
        state = build_state(cwd=cwd)
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")

        # Execute — tag_create should succeed, push_tag will fail (no remote)
        result = execute_plan(plan, cwd=cwd)
        # tag_create should succeed
        tag_result = result.results[0]
        assert tag_result.step == "tag_create"
        assert tag_result.ok is True
        assert tag_result.details["tag"] == "v0.1.0"

        # Verify tag exists
        check = subprocess.run(
            ["git", "tag", "-l", "v0.1.0"],
            cwd=tmp_git_repo, capture_output=True, text=True,
        )
        assert "v0.1.0" in check.stdout

    def test_push_tag_fails_without_remote(self, tmp_git_repo: Path):
        """push_tag should fail when no remote is configured."""
        from jetsam.core.state import build_state

        cwd = str(tmp_git_repo)
        state = build_state(cwd=cwd)
        plan = plan_release(state, plan_id="p_test", tag="v0.2.0")
        result = execute_plan(plan, cwd=cwd)

        # tag_create succeeds, push_tag fails (no remote)
        assert result.status == "partial"
        assert result.results[0].ok is True  # tag_create
        assert result.results[1].ok is False  # push_tag


# --- Release CLI ---


class TestReleaseCLI:
    def test_dry_run(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["release", "v0.1.0", "--dry-run"],
            obj={"json": False},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "v0.1.0" in result.output

    def test_dry_run_json(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "release", "v0.1.0", "--dry-run"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verb"] == "release"
        assert data["plan_id"].startswith("p_")

    def test_dry_run_with_title(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["release", "v0.1.0", "--title", "First Release", "--dry-run"],
            obj={"json": False},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "First Release" in result.output

    def test_alias_r(self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_git_repo)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["r", "v0.1.0", "--dry-run"],
            obj={"json": False},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "v0.1.0" in result.output


# --- Alias Generation ---


class TestAliasGeneration:
    def test_posix_block(self):
        block = generate_alias_block_posix()
        assert ALIAS_MARKER in block
        assert "alias jt='jetsam'" in block
        assert "alias jts='jetsam status'" in block
        assert "alias jth='jetsam ship'" in block
        assert "alias jtw='jetsam switch'" in block

    def test_fish_block(self):
        block = generate_alias_block_fish()
        assert ALIAS_MARKER in block
        assert "function jt; jetsam $argv; end" in block
        assert "function jts; jetsam status $argv; end" in block

    def test_marker_detection(self):
        assert has_alias_marker(f"some stuff\n{ALIAS_MARKER}\nalias jt='jetsam'\n")
        assert not has_alias_marker("some stuff\nalias jt='jetsam'\n")

    def test_idempotency(self):
        """Block already present should be detected."""
        block = generate_alias_block_posix()
        assert has_alias_marker(block)


class TestInitAliases:
    def test_init_aliases_flag(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ):
        monkeypatch.chdir(tmp_git_repo)
        # Point HOME to a temp directory so we don't modify real shell config
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("SHELL", "/bin/bash")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["init", "--aliases"],
            obj={"json": False},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Aliases" in result.output or "aliases" in result.output

        # Check that .bashrc was created
        bashrc = fake_home / ".bashrc"
        assert bashrc.exists()
        content = bashrc.read_text()
        assert ALIAS_MARKER in content
        assert "alias jt='jetsam'" in content

    def test_init_aliases_idempotent(
        self, tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ):
        monkeypatch.chdir(tmp_git_repo)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("SHELL", "/bin/bash")

        runner = CliRunner()
        # Run twice
        runner.invoke(cli, ["init", "--aliases"], obj={"json": False}, catch_exceptions=False)
        result = runner.invoke(
            cli, ["init", "--aliases"], obj={"json": False}, catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "already installed" in result.output

        # Check marker appears only once
        bashrc = (fake_home / ".bashrc").read_text()
        assert bashrc.count(ALIAS_MARKER) == 2  # start + end markers from first install only


# --- Worktree Shared Paths ---


class TestWorktreeSharedPaths:
    def test_symlinks_created(self, tmp_git_repo: Path):
        """Shared paths should be symlinked into new worktree."""
        repo_root = str(tmp_git_repo)

        # Create shared paths config
        (tmp_git_repo / ".git-worktree-shared").write_text(".env\nnode_modules\n")
        (tmp_git_repo / ".env").write_text("SECRET=123\n")
        (tmp_git_repo / "node_modules").mkdir()
        (tmp_git_repo / "node_modules" / "pkg").mkdir()

        # Create a fake worktree directory
        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert ".env" in linked
        assert "node_modules" in linked

        # Verify symlinks
        assert (wt_path / ".env").is_symlink()
        assert (wt_path / "node_modules").is_symlink()
        assert (wt_path / ".env").read_text() == "SECRET=123\n"

    def test_existing_symlink_skipped(self, tmp_git_repo: Path):
        """Existing symlinks should not be recreated."""
        repo_root = str(tmp_git_repo)
        (tmp_git_repo / ".git-worktree-shared").write_text(".env\n")
        (tmp_git_repo / ".env").write_text("SECRET=123\n")

        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        # Create symlink manually
        os.symlink(str(tmp_git_repo / ".env"), str(wt_path / ".env"))

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert linked == []  # Nothing new linked

    def test_missing_source_skipped(self, tmp_git_repo: Path):
        """Missing source paths should be silently skipped."""
        repo_root = str(tmp_git_repo)
        (tmp_git_repo / ".git-worktree-shared").write_text("nonexistent\n")

        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert linked == []

    def test_no_shared_file(self, tmp_git_repo: Path):
        """No .git-worktree-shared file should result in no links."""
        repo_root = str(tmp_git_repo)
        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert linked == []

    def test_comments_ignored(self, tmp_git_repo: Path):
        """Lines starting with # should be ignored."""
        repo_root = str(tmp_git_repo)
        (tmp_git_repo / ".git-worktree-shared").write_text("# comment\n.env\n\n")
        (tmp_git_repo / ".env").write_text("SECRET=123\n")

        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert linked == [".env"]

    def test_nested_path(self, tmp_git_repo: Path):
        """Paths with directories should have parents created."""
        repo_root = str(tmp_git_repo)
        (tmp_git_repo / ".git-worktree-shared").write_text("config/local.yml\n")
        (tmp_git_repo / "config").mkdir()
        (tmp_git_repo / "config" / "local.yml").write_text("key: val\n")

        wt_path = tmp_git_repo / ".worktrees" / "feature"
        wt_path.mkdir(parents=True)

        linked = setup_shared_paths(repo_root, str(wt_path))
        assert "config/local.yml" in linked
        assert (wt_path / "config" / "local.yml").is_symlink()


# --- Error Recovery Suggestions ---


class TestErrorRecovery:
    def test_push_rejected(self):
        suggestion = _suggest_recovery("push", "rejected: non-fast-forward")
        assert suggestion == "sync"

    def test_push_non_fast_forward(self):
        suggestion = _suggest_recovery("push", "error: failed to push, fetch first")
        assert suggestion == "sync"

    def test_rebase_conflict(self):
        suggestion = _suggest_recovery("rebase", "CONFLICT (content): merge conflict in foo.py")
        assert suggestion is not None
        assert "rebase --continue" in suggestion

    def test_checkout_dirty(self):
        suggestion = _suggest_recovery(
            "checkout", "error: Your local changes would be overwritten",
        )
        assert suggestion is not None
        assert "save" in suggestion or "stash" in suggestion

    def test_merge_conflict(self):
        suggestion = _suggest_recovery("merge", "CONFLICT: Merge conflict in file.py")
        assert suggestion is not None
        assert "merge --continue" in suggestion

    def test_tag_exists(self):
        suggestion = _suggest_recovery("tag_create", "fatal: tag 'v1.0' already exists")
        assert suggestion is not None
        assert "tag -d" in suggestion

    def test_unknown_error_returns_none(self):
        suggestion = _suggest_recovery("push", "some random error")
        assert suggestion is None

    def test_stale_plan_has_suggestion(self, dirty_git_repo: Path):
        """When repo state changes, stale_plan error should include suggestion."""
        cwd = str(dirty_git_repo)
        state = RepoState(
            branch="main",
            upstream=None,
            default_branch="main",
            dirty=True,
            staged=["staged.py"],
            unstaged=["README.md"],
            untracked=["scratch.txt"],
            ahead=0,
            behind=0,
            stash_count=0,
            platform="",
            remote="",
            remote_url="",
            head_sha="abc123",
            repo_root=cwd,
        )

        from jetsam.core.planner import plan_save

        plan = plan_save(state, plan_id="p_test", message="test save")

        # Modify repo to make state stale
        (dirty_git_repo / "new_file.txt").write_text("new\n")

        result = execute_plan(plan, cwd=cwd)
        assert result.status == "failed"
        assert result.results[0].error == "stale_plan"
        assert "suggested_action" in result.results[0].details

    def test_failed_step_gets_suggestion(self, tmp_git_repo: Path):
        """A failed push step should get a suggested_action in details."""
        from jetsam.core.state import build_state

        cwd = str(tmp_git_repo)
        state = build_state(cwd=cwd)
        plan = plan_release(state, plan_id="p_test", tag="v0.1.0")
        result = execute_plan(plan, cwd=cwd)

        # tag_create succeeds, push_tag fails (no remote)
        assert result.status == "partial"
