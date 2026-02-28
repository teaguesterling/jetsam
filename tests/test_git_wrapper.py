"""Tests for the git wrapper."""

import asyncio

import pytest

from jetsam.git.wrapper import GitError, GitResult, run_git, run_git_sync


class TestGitResult:
    def test_ok(self):
        r = GitResult(returncode=0, stdout="ok", stderr="")
        assert r.ok

    def test_not_ok(self):
        r = GitResult(returncode=1, stdout="", stderr="error")
        assert not r.ok


class TestRunGitSync:
    def test_version(self):
        result = run_git_sync(["--version"])
        assert result.ok
        assert "git version" in result.stdout

    def test_invalid_command(self):
        result = run_git_sync(["not-a-real-command"])
        assert not result.ok

    def test_check_raises(self):
        with pytest.raises(GitError):
            run_git_sync(["not-a-real-command"], check=True)


class TestRunGitAsync:
    def test_version(self):
        result = asyncio.get_event_loop().run_until_complete(run_git(["--version"]))
        assert result.ok
        assert "git version" in result.stdout

    def test_invalid_command(self):
        result = asyncio.get_event_loop().run_until_complete(run_git(["not-a-real-command"]))
        assert not result.ok
