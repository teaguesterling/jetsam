"""Tests for repository state snapshot."""

from pathlib import Path

from jetsam.core.state import RepoState, _is_jetsam_path, attach_open_pr, build_state
from jetsam.platforms.base import PRDetails


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

        # Modify a TRACKED file — an unstaged change must change the hash.
        # (A new *untracked* file deliberately does not; see
        # test_unscoped_hash_stable_across_untracked_churn_e2e.)
        (tmp_git_repo / "README.md").write_text("# Test\nmodified\n")

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

    def test_unscoped_hash_ignores_untracked_churn(self):
        """Untracked-file churn (agent-runtime dirs like .kibitzer/, .bird/) must
        not change the unscoped hash — generalizes the #12 .jetsam/ fix so such
        dirs don't cause stale_plan on start/sync."""
        base = dict(
            branch="feature", upstream="origin/feature", default_branch="main",
            dirty=True, staged=[], unstaged=[], untracked=[".kibitzer/a"],
            ahead=0, behind=0, stash_count=0,
            platform="github", remote="user/repo",
            remote_url="git@github.com:user/repo.git",
            head_sha="abc123", repo_root="/tmp/repo",
        )
        s1 = RepoState(**base)
        s2 = RepoState(**{**base, "untracked": [".kibitzer/a", ".bird/log", "scratch.txt"]})
        assert s1.compute_hash() == s2.compute_hash()

    def test_unscoped_hash_reflects_tracked_changes(self):
        """Sanity: excluding untracked must not also drop tracked changes."""
        base = dict(
            branch="feature", upstream="origin/feature", default_branch="main",
            dirty=False, staged=[], unstaged=[], untracked=[],
            ahead=0, behind=0, stash_count=0,
            platform="github", remote="user/repo",
            remote_url="git@github.com:user/repo.git",
            head_sha="abc123", repo_root="/tmp/repo",
        )
        s1 = RepoState(**base)
        s2 = RepoState(**{**base, "staged": ["src/x.py"]})
        assert s1.compute_hash() != s2.compute_hash()

    def test_unscoped_hash_stable_across_untracked_churn_e2e(self, tmp_git_repo: Path):
        """End-to-end: creating an arbitrary untracked dir must not change the
        unscoped hash (the stale_plan-on-confirm bug for non-.jetsam dirs)."""
        hash_before = build_state(cwd=str(tmp_git_repo)).compute_hash()
        kb = tmp_git_repo / ".kibitzer"
        kb.mkdir()
        (kb / "session.json").write_text('{"a": 1}\n')
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


class _FakePlatform:
    def __init__(self, pr: PRDetails | None):
        self._pr = pr
        self.lookups = 0

    def pr_for_branch(self, branch: str) -> PRDetails | None:
        self.lookups += 1
        return self._pr


def _feature_state(**kwargs) -> RepoState:
    defaults = dict(
        branch="feature", upstream="origin/feature", default_branch="main",
        dirty=False, staged=[], unstaged=[], untracked=[],
        ahead=0, behind=0, stash_count=0,
        platform="github", remote="user/repo",
        remote_url="git@github.com:user/repo.git",
        head_sha="abc123", repo_root="/tmp/repo",
    )
    defaults.update(kwargs)
    return RepoState(**defaults)


class TestAttachOpenPr:
    """attach_open_pr is what makes finish able to plan pr_merge —
    build_state() alone always leaves state.pr None."""

    def _patch_platform(self, monkeypatch, platform):
        monkeypatch.setattr(
            "jetsam.platforms.get_platform", lambda name, cwd=None: platform
        )

    def test_open_pr_attached(self, monkeypatch):
        pr = PRDetails(number=7, state="open", title="Add thing", url="u", mergeable=True)
        self._patch_platform(monkeypatch, _FakePlatform(pr))

        state = attach_open_pr(_feature_state())
        assert state.pr is not None
        assert state.pr.number == 7
        assert state.pr.state == "open"
        assert state.pr.mergeable is True

    def test_merged_pr_not_attached(self, monkeypatch):
        """pr_for_branch returns the most recent PR even when merged —
        finish must never plan a re-merge of it."""
        pr = PRDetails(number=7, state="merged", title="Old", url="u")
        self._patch_platform(monkeypatch, _FakePlatform(pr))

        state = attach_open_pr(_feature_state())
        assert state.pr is None

    def test_no_pr_leaves_none(self, monkeypatch):
        self._patch_platform(monkeypatch, _FakePlatform(None))
        state = attach_open_pr(_feature_state())
        assert state.pr is None

    def test_default_branch_skips_lookup(self, monkeypatch):
        platform = _FakePlatform(PRDetails(number=1, state="open", title="x"))
        self._patch_platform(monkeypatch, platform)

        state = attach_open_pr(_feature_state(branch="main"))
        assert state.pr is None
        assert platform.lookups == 0

    def test_unknown_platform_is_noop(self, monkeypatch):
        self._patch_platform(monkeypatch, None)
        state = attach_open_pr(_feature_state(platform="unknown"))
        assert state.pr is None
