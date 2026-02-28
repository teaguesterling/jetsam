"""Tests for CLI verb commands."""

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from jetsam.cli.main import cli


class TestStatusVerb:
    def test_human_output(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["status"], env={"GIT_DIR": str(tmp_git_repo / ".git"),
                                                     "GIT_WORK_TREE": str(tmp_git_repo)})
        # Click runner doesn't change cwd, so we test via env or monkeypatch
        # For now, test that the command doesn't crash
        assert result.exit_code == 0

    def test_json_output(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--json", "status"],
                               env={"GIT_DIR": str(tmp_git_repo / ".git"),
                                    "GIT_WORK_TREE": str(tmp_git_repo)})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "branch" in data
        assert "dirty" in data


class TestSaveVerb:
    def test_dry_run_json(self, dirty_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "save", "--dry-run", "-m", "test commit"],
            env={"GIT_DIR": str(dirty_git_repo / ".git"),
                 "GIT_WORK_TREE": str(dirty_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_id" in data
        assert "steps" in data

    def test_execute(self, dirty_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "save", "--execute", "-m", "auto save"],
            env={"GIT_DIR": str(dirty_git_repo / ".git"),
                 "GIT_WORK_TREE": str(dirty_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

        # Verify commit was made
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=str(dirty_git_repo),
        )
        assert "auto save" in log_result.stdout


class TestLogVerb:
    def test_human_output(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["log"],
            env={"GIT_DIR": str(tmp_git_repo / ".git"),
                 "GIT_WORK_TREE": str(tmp_git_repo)},
        )
        assert result.exit_code == 0
        assert "initial" in result.output

    def test_json_output(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "log", "-n", "1"],
            env={"GIT_DIR": str(tmp_git_repo / ".git"),
                 "GIT_WORK_TREE": str(tmp_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["message"] == "initial"


class TestDiffVerb:
    def test_stat_output(self, dirty_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "diff", "--stat"],
            env={"GIT_DIR": str(dirty_git_repo / ".git"),
                 "GIT_WORK_TREE": str(dirty_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "files_changed" in data
        assert data["files_changed"] > 0

    def test_staged_diff(self, dirty_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "diff", "--stat", "--staged"],
            env={"GIT_DIR": str(dirty_git_repo / ".git"),
                 "GIT_WORK_TREE": str(dirty_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["files_changed"] >= 1  # staged.py is staged


class TestPassthrough:
    def test_git_branch(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["branch"],
            env={"GIT_DIR": str(tmp_git_repo / ".git"),
                 "GIT_WORK_TREE": str(tmp_git_repo)},
        )
        assert result.exit_code == 0
        assert "main" in result.output

    def test_git_branch_json(self, tmp_git_repo: Path):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "branch"],
            env={"GIT_DIR": str(tmp_git_repo / ".git"),
                 "GIT_WORK_TREE": str(tmp_git_repo)},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
