"""Tests for worktree parsing and detection."""

import os
import subprocess
from pathlib import Path

from jetsam.git.parsers import parse_worktree_list
from jetsam.worktree.integration import (
    create_worktree,
    detect_worktree,
    list_worktrees,
    prune_worktrees,
    remove_worktree,
)


class TestParseWorktreeList:
    def test_single_worktree(self):
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
        )
        entries = parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].path == "/home/user/repo"
        assert entries[0].head == "abc123"
        assert entries[0].branch == "main"
        assert entries[0].is_bare is False
        assert entries[0].prunable is False

    def test_multiple_worktrees(self):
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /home/user/repo/.worktrees/feature\n"
            "HEAD def456\n"
            "branch refs/heads/feature\n"
            "\n"
        )
        entries = parse_worktree_list(output)
        assert len(entries) == 2
        assert entries[0].branch == "main"
        assert entries[1].branch == "feature"
        assert entries[1].path == "/home/user/repo/.worktrees/feature"

    def test_detached_head(self):
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /tmp/wt\n"
            "HEAD def456\n"
            "detached\n"
            "\n"
        )
        entries = parse_worktree_list(output)
        assert entries[1].branch == "(detached)"

    def test_bare_repo(self):
        output = (
            "worktree /home/user/repo.git\n"
            "HEAD abc123\n"
            "bare\n"
            "\n"
        )
        entries = parse_worktree_list(output)
        assert entries[0].is_bare is True

    def test_prunable(self):
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /tmp/gone\n"
            "HEAD def456\n"
            "branch refs/heads/old\n"
            "prunable\n"
            "\n"
        )
        entries = parse_worktree_list(output)
        assert entries[1].prunable is True

    def test_empty_output(self):
        entries = parse_worktree_list("")
        assert entries == []

    def test_no_trailing_newline(self):
        output = (
            "worktree /home/user/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main"
        )
        entries = parse_worktree_list(output)
        assert len(entries) == 1
        assert entries[0].branch == "main"


class TestDetectWorktree:
    def test_no_worktrees(self, tmp_git_repo: Path):
        result = detect_worktree(cwd=str(tmp_git_repo))
        assert result is None  # Single worktree = not in worktree mode

    def test_with_worktree(self, tmp_git_repo: Path):
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }

        wt_path = str(tmp_git_repo / ".worktrees" / "feature")
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", wt_path],
            cwd=tmp_git_repo, check=True, env=env, capture_output=True,
        )

        # From main worktree — should detect worktrees exist but not active
        state = detect_worktree(cwd=str(tmp_git_repo))
        assert state is not None
        assert state.active is False
        assert len(state.worktrees) == 2

        # From secondary worktree — should be active
        state2 = detect_worktree(cwd=wt_path)
        assert state2 is not None
        assert state2.active is True

        # Clean up
        subprocess.run(
            ["git", "worktree", "remove", wt_path],
            cwd=tmp_git_repo, check=True, env=env, capture_output=True,
        )


class TestWorktreeOperations:
    def test_list_worktrees(self, tmp_git_repo: Path):
        entries = list_worktrees(cwd=str(tmp_git_repo))
        assert len(entries) == 1
        assert entries[0].branch == "main"

    def test_create_and_remove_worktree(self, tmp_git_repo: Path):
        wt_path = str(tmp_git_repo / ".worktrees" / "test-branch")

        ok = create_worktree(
            path=wt_path,
            branch="test-branch",
            new_branch=True,
            cwd=str(tmp_git_repo),
        )
        assert ok is True

        entries = list_worktrees(cwd=str(tmp_git_repo))
        assert len(entries) == 2
        branches = [e.branch for e in entries]
        assert "test-branch" in branches

        ok = remove_worktree(path=wt_path, cwd=str(tmp_git_repo))
        assert ok is True

        entries = list_worktrees(cwd=str(tmp_git_repo))
        assert len(entries) == 1

    def test_prune_worktrees(self, tmp_git_repo: Path):
        ok = prune_worktrees(cwd=str(tmp_git_repo))
        assert ok is True
