"""Tests for repository state snapshot."""

from pathlib import Path

from jetsam.core.state import RepoState, _is_jetsam_path, build_state


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

    def test_compute_hash_exclude_remote_tracking(self):
        """compute_hash with exclude_remote_tracking should ignore ahead/behind."""
        base = dict(
            branch="feature", upstream="origin/feature", default_branch="main",
            dirty=False, staged=[], unstaged=[], untracked=[],
            ahead=0, behind=0, stash_count=0,
            platform="github", remote="user/repo",
            remote_url="git@github.com:user/repo.git",
            head_sha="abc123", repo_root="/tmp/repo",
        )
        state1 = RepoState(**base)
        state2 = RepoState(**{**base, "ahead": 2, "behind": 5})

        hash1 = state1.compute_hash(exclude_remote_tracking=True)
        hash2 = state2.compute_hash(exclude_remote_tracking=True)
        assert hash1 == hash2

    def test_jetsam_dir_excluded_from_state(self, tmp_git_repo: Path):
        """jetsam's own .jetsam/ dir must not appear in the snapshot."""
        plans = tmp_git_repo / ".jetsam" / "plans"
        plans.mkdir(parents=True)
        (plans / "p_abc.json").write_text("{}\n")

        state = build_state(cwd=str(tmp_git_repo))
        assert not state.dirty
        assert state.untracked == []
        assert all(not p.startswith(".jetsam") for p in state.untracked)

    def test_state_hash_stable_across_jetsam_writes(self, tmp_git_repo: Path):
        """Writing a plan into .jetsam/ must not change the state hash —
        this is the stale_plan-on-confirm regression (see issue #12)."""
        hash_before = build_state(cwd=str(tmp_git_repo)).compute_hash()

        plans = tmp_git_repo / ".jetsam" / "plans"
        plans.mkdir(parents=True)
        (plans / "p_abc.json").write_text('{"plan": 1}\n')

        hash_after = build_state(cwd=str(tmp_git_repo)).compute_hash()
        assert hash_before == hash_after

    def test_is_jetsam_path(self):
        assert _is_jetsam_path(".jetsam")
        assert _is_jetsam_path(".jetsam/")
        assert _is_jetsam_path(".jetsam/plans/p_abc.json")
        assert _is_jetsam_path(".jetsam/config.yaml")
        assert not _is_jetsam_path(".jetsamrc")
        assert not _is_jetsam_path("src/.jetsam/x")
        assert not _is_jetsam_path("README.md")

    def test_compute_hash_default_includes_remote_tracking(self):
        """Default compute_hash should still include ahead/behind."""
        base = dict(
            branch="feature", upstream="origin/feature", default_branch="main",
            dirty=False, staged=[], unstaged=[], untracked=[],
            ahead=0, behind=0, stash_count=0,
            platform="github", remote="user/repo",
            remote_url="git@github.com:user/repo.git",
            head_sha="abc123", repo_root="/tmp/repo",
        )
        state1 = RepoState(**base)
        state2 = RepoState(**{**base, "ahead": 2, "behind": 5})

        hash1 = state1.compute_hash()
        hash2 = state2.compute_hash()
        assert hash1 != hash2
