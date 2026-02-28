"""Shared test fixtures."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()

    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"}

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, env=env,
                   capture_output=True)
    # Create initial file and commit
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, env=env,
                   capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, env=env,
                   capture_output=True)

    return repo


@pytest.fixture
def dirty_git_repo(tmp_git_repo: Path) -> Path:
    """Create a git repo with staged, unstaged, and untracked files."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"}

    # Staged file
    (tmp_git_repo / "staged.py").write_text("staged = True\n")
    subprocess.run(["git", "add", "staged.py"], cwd=tmp_git_repo, check=True, env=env,
                   capture_output=True)

    # Unstaged modification
    (tmp_git_repo / "README.md").write_text("# Modified\n")

    # Untracked file
    (tmp_git_repo / "scratch.txt").write_text("scratch\n")

    return tmp_git_repo
