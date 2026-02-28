"""Integration tests — full CLI flows with real git repos."""

import json
import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

from jetsam.cli.main import cli


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the repo."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def _invoke(args: list[str], repo: Path) -> object:
    """Invoke jetsam CLI against a repo."""
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={
            "GIT_DIR": str(repo / ".git"),
            "GIT_WORK_TREE": str(repo),
        },
    )


class TestFullSaveFlow:
    """Test the complete save workflow: plan → execute → verify."""

    def test_save_modified_files(self, dirty_git_repo: Path):
        """Save should stage modified tracked files and commit."""
        result = _invoke(["--json", "save", "--execute", "-m", "save modified"], dirty_git_repo)

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # Verify the commit
        log = _git(dirty_git_repo, "log", "--oneline", "-1")
        assert "save modified" in log.stdout

    def test_save_with_include_pattern(self, tmp_git_repo: Path):
        """Save with --include should only stage matching files."""
        # Create files
        (tmp_git_repo / "src").mkdir()
        (tmp_git_repo / "src" / "main.py").write_text("code\n")
        (tmp_git_repo / "src" / "test.py").write_text("test\n")
        (tmp_git_repo / "docs.md").write_text("docs\n")
        _git(tmp_git_repo, "add", ".")
        _git(tmp_git_repo, "commit", "-m", "add files")

        # Modify all files
        (tmp_git_repo / "src" / "main.py").write_text("changed code\n")
        (tmp_git_repo / "src" / "test.py").write_text("changed test\n")
        (tmp_git_repo / "docs.md").write_text("changed docs\n")

        # Save only src/*.py
        result = _invoke(
            ["--json", "save", "--execute", "-m", "update src",
             "--include", "src/*.py"],
            tmp_git_repo,
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # Verify docs.md is still modified (not committed)
        status = _git(tmp_git_repo, "status", "--porcelain")
        assert "docs.md" in status.stdout

    def test_save_with_explicit_files(self, dirty_git_repo: Path):
        """Save with positional files should stage only specified files."""
        result = _invoke(
            ["--json", "save", "--execute", "-m", "specific save",
             "scratch.txt"],
            dirty_git_repo,
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # README.md should still be modified
        status = _git(dirty_git_repo, "status", "--porcelain")
        assert "README.md" in status.stdout

    def test_save_dry_run(self, dirty_git_repo: Path):
        """Dry run should return plan without executing."""
        result = _invoke(
            ["--json", "save", "--dry-run", "-m", "should not commit"],
            dirty_git_repo,
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_id" in data
        assert "steps" in data

        # Verify nothing was committed
        log = _git(dirty_git_repo, "log", "--oneline")
        assert "should not commit" not in log.stdout


class TestFullStatusFlow:
    """Test the status command."""

    def test_status_clean(self, tmp_git_repo: Path):
        result = _invoke(["--json", "status"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["branch"] == "main"
        assert data["dirty"] is False
        assert data["staged"] == []

    def test_status_dirty(self, dirty_git_repo: Path):
        result = _invoke(["--json", "status"], dirty_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dirty"] is True
        assert len(data["staged"]) > 0
        assert len(data["unstaged"]) > 0
        assert len(data["untracked"]) > 0

    def test_status_human(self, tmp_git_repo: Path):
        result = _invoke(["status"], tmp_git_repo)
        assert result.exit_code == 0
        assert "main" in result.output
        assert "Clean" in result.output


class TestFullLogFlow:
    """Test the log command."""

    def test_log_json(self, tmp_git_repo: Path):
        result = _invoke(["--json", "log", "-n", "1"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["message"] == "initial"

    def test_log_human(self, tmp_git_repo: Path):
        result = _invoke(["log"], tmp_git_repo)
        assert result.exit_code == 0
        assert "initial" in result.output

    def test_log_multiple_commits(self, tmp_git_repo: Path):
        # Create more commits
        for i in range(3):
            (tmp_git_repo / f"file{i}.txt").write_text(f"content {i}\n")
            _git(tmp_git_repo, "add", f"file{i}.txt")
            _git(tmp_git_repo, "commit", "-m", f"commit {i}")

        result = _invoke(["--json", "log", "-n", "4"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4


class TestFullDiffFlow:
    """Test the diff command."""

    def test_diff_stat_json(self, dirty_git_repo: Path):
        result = _invoke(["--json", "diff", "--stat"], dirty_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["files_changed"] > 0

    def test_diff_staged_json(self, dirty_git_repo: Path):
        result = _invoke(["--json", "diff", "--stat", "--staged"], dirty_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["files_changed"] >= 1  # staged.py

    def test_diff_human(self, dirty_git_repo: Path):
        result = _invoke(["diff"], dirty_git_repo)
        assert result.exit_code == 0
        # Should show the actual diff content
        assert "README" in result.output or "Modified" in result.output


class TestPassthroughFlow:
    """Test pass-through to git commands."""

    def test_git_branch(self, tmp_git_repo: Path):
        result = _invoke(["branch"], tmp_git_repo)
        assert result.exit_code == 0
        assert "main" in result.output

    def test_git_branch_json(self, tmp_git_repo: Path):
        result = _invoke(["--json", "branch"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "main" in data["output"]

    def test_git_rev_parse_passthrough(self, tmp_git_repo: Path):
        """rev-parse is not a jetsam verb, should pass through."""
        result = _invoke(["rev-parse", "HEAD"], tmp_git_repo)
        assert result.exit_code == 0
        assert len(result.output.strip()) == 40  # full SHA

    def test_git_stash_list(self, tmp_git_repo: Path):
        """stash is not a jetsam verb, should pass through."""
        result = _invoke(["stash", "list"], tmp_git_repo)
        assert result.exit_code == 0


class TestSyncDryRun:
    """Test sync command dry-run (can't test full sync without remote)."""

    def test_sync_dry_run(self, tmp_git_repo: Path):
        result = _invoke(["--json", "sync", "--dry-run"], tmp_git_repo)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_id" in data
        assert "steps" in data
        actions = [s["action"] for s in data["steps"]]
        assert "fetch" in actions


class TestMultipleCommitFlow:
    """Test multiple saves in sequence."""

    def test_sequential_saves(self, tmp_git_repo: Path):
        for i in range(3):
            (tmp_git_repo / f"file{i}.py").write_text(f"content {i}\n")
            result = _invoke(
                ["--json", "save", "--execute", "-m", f"save {i}",
                 f"file{i}.py"],
                tmp_git_repo,
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["status"] == "ok"

        # Verify all commits exist
        log_result = _invoke(["--json", "log", "-n", "4"], tmp_git_repo)
        data = json.loads(log_result.output)
        messages = [e["message"] for e in data]
        assert "save 0" in messages
        assert "save 1" in messages
        assert "save 2" in messages
