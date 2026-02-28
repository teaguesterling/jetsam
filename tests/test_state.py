"""Tests for repository state snapshot."""

from pathlib import Path

from jetsam.core.state import build_state


class TestBuildState:
    def test_clean_repo(self, tmp_git_repo: Path):
        state = build_state(cwd=str(tmp_git_repo))
        assert state.branch == "main"
        assert state.default_branch == "main"
        assert not state.dirty
        assert state.staged == []
        assert state.unstaged == []
        assert state.untracked == []
        assert state.stash_count == 0
        assert state.head_sha != ""
        assert state.repo_root == str(tmp_git_repo)

    def test_dirty_repo(self, dirty_git_repo: Path):
        state = build_state(cwd=str(dirty_git_repo))
        assert state.dirty
        assert "staged.py" in state.staged
        assert "README.md" in state.unstaged
        assert "scratch.txt" in state.untracked

    def test_platform_unknown_for_local(self, tmp_git_repo: Path):
        state = build_state(cwd=str(tmp_git_repo))
        assert state.platform == "unknown"
        assert state.remote == ""

    def test_state_hash_changes_on_modification(self, tmp_git_repo: Path):
        state1 = build_state(cwd=str(tmp_git_repo))
        hash1 = state1.compute_hash()

        # Create a new file
        (tmp_git_repo / "new.py").write_text("new\n")

        state2 = build_state(cwd=str(tmp_git_repo))
        hash2 = state2.compute_hash()

        assert hash1 != hash2

    def test_state_hash_scoped(self, dirty_git_repo: Path):
        state = build_state(cwd=str(dirty_git_repo))

        # Hash scoped to staged.py should differ from hash scoped to README.md
        hash_staged = state.compute_hash(scope=["staged.py"])
        hash_readme = state.compute_hash(scope=["README.md"])

        assert hash_staged != hash_readme

    def test_to_dict(self, tmp_git_repo: Path):
        state = build_state(cwd=str(tmp_git_repo))
        d = state.to_dict()
        assert d["branch"] == "main"
        assert "_state_hash" not in d
        assert isinstance(d["staged"], list)

    def test_ahead_behind_zero(self, tmp_git_repo: Path):
        state = build_state(cwd=str(tmp_git_repo))
        assert state.ahead == 0
        assert state.behind == 0
