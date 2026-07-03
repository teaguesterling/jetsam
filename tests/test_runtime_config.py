"""Tests for the in-memory runtime config + MCP config() tool."""

from __future__ import annotations

import pytest

from jetsam.config import runtime as rt
from jetsam.config.runtime import (
    JetsamRuntimeConfig,
    get_runtime,
    reset_runtime,
    update_runtime,
)


@pytest.fixture(autouse=True)
def _isolate_runtime():
    """Reset the module singleton + seed between tests so order doesn't matter."""
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()
    yield
    rt._runtime = JetsamRuntimeConfig()
    rt._seed = JetsamRuntimeConfig()


class TestFromEnv:
    def test_empty_env_returns_defaults(self):
        cfg = JetsamRuntimeConfig.from_env(env={})
        assert cfg.active_root is None
        assert cfg.log_level == "info"
        assert cfg.default_sync_strategy == "rebase"
        assert cfg.signing_required is False

    def test_active_root_from_env(self):
        cfg = JetsamRuntimeConfig.from_env(env={"JETSAM_ACTIVE_ROOT": "/tmp/repo"})
        assert cfg.active_root == "/tmp/repo"

    def test_log_level_normalized_lowercase(self):
        cfg = JetsamRuntimeConfig.from_env(env={"JETSAM_LOG_LEVEL": "DEBUG"})
        assert cfg.log_level == "debug"

    def test_log_level_invalid_falls_back_to_default(self):
        cfg = JetsamRuntimeConfig.from_env(env={"JETSAM_LOG_LEVEL": "verbose"})
        assert cfg.log_level == "info"

    def test_signing_required_truthy(self):
        for v in ("true", "1", "yes", "on", "TRUE"):
            cfg = JetsamRuntimeConfig.from_env(env={"JETSAM_SIGNING_REQUIRED": v})
            assert cfg.signing_required is True, f"failed for {v!r}"

    def test_signing_required_falsy(self):
        for v in ("false", "0", "no", "off", ""):
            cfg = JetsamRuntimeConfig.from_env(env={"JETSAM_SIGNING_REQUIRED": v})
            assert cfg.signing_required is False, f"failed for {v!r}"


class TestUpdateRuntime:
    def test_set_active_root_persists_in_singleton(self):
        update_runtime({"active_root": "/tmp/x"})
        assert get_runtime().active_root == "/tmp/x"

    def test_unknown_key_raises_and_leaves_unchanged(self):
        original = get_runtime().to_dict()
        with pytest.raises(ValueError, match="unknown config key"):
            update_runtime({"bogus": "value"})
        assert get_runtime().to_dict() == original

    def test_invalid_value_raises_and_leaves_unchanged(self):
        original = get_runtime().to_dict()
        with pytest.raises(ValueError, match="log_level"):
            update_runtime({"log_level": "verbose"})
        assert get_runtime().to_dict() == original

    def test_atomic_batch_set_either_all_or_none(self):
        original = get_runtime().to_dict()
        with pytest.raises(ValueError):
            update_runtime({"active_root": "/tmp/y", "log_level": "verbose"})
        # active_root should NOT have been applied even though it's valid
        assert get_runtime().to_dict() == original

    def test_signing_required_type_strict(self):
        with pytest.raises(ValueError, match="signing_required"):
            update_runtime({"signing_required": "true"})  # string, not bool

    def test_removed_auto_confirm_key_is_rejected_as_unknown(self):
        # The dead auto_confirm_safe_verbs knob was removed; setting it now
        # fails as an unknown key rather than being silently accepted.
        with pytest.raises(ValueError, match="unknown config key"):
            update_runtime({"auto_confirm_safe_verbs": ["save"]})


class TestResetRuntime:
    def test_reset_reverts_to_seed(self, monkeypatch):
        # Simulate launch-time env seed
        monkeypatch.setenv("JETSAM_ACTIVE_ROOT", "/tmp/seeded")
        rt._seed = JetsamRuntimeConfig.from_env()
        rt._runtime = JetsamRuntimeConfig.from_env()
        # Override at runtime
        update_runtime({"active_root": "/tmp/overridden"})
        assert get_runtime().active_root == "/tmp/overridden"
        # Reset goes back to seed (not dataclass defaults)
        reset_runtime()
        assert get_runtime().active_root == "/tmp/seeded"

    def test_reset_with_no_env_goes_to_defaults(self):
        update_runtime({"active_root": "/tmp/x"})
        reset_runtime()
        assert get_runtime().active_root is None
        assert get_runtime().log_level == "info"


class TestBuildStateRespectsActiveRoot:
    """When cwd is not passed, build_state falls back to active_root."""

    def test_falls_back_to_active_root_when_cwd_missing(self, tmp_path, monkeypatch):
        # Initialize a tiny repo at tmp_path
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t",
             "-c", "user.name=t", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path, check=True, capture_output=True,
        )

        # chdir somewhere that's NOT a repo, and set active_root to tmp_path
        elsewhere = tmp_path.parent / "not_a_repo"
        elsewhere.mkdir(exist_ok=True)
        monkeypatch.chdir(elsewhere)
        update_runtime({"active_root": str(tmp_path)})

        from jetsam.core.state import build_state
        state = build_state()  # no cwd= passed
        assert state.repo_root.startswith(str(tmp_path)), (
            f"build_state should have used active_root={tmp_path}, "
            f"got repo_root={state.repo_root!r}"
        )

    def test_explicit_cwd_still_wins_over_active_root(self, tmp_path, monkeypatch):
        # Two repos: A (active_root) and B (explicit cwd= target)
        import subprocess
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        for repo in (repo_a, repo_b):
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t",
                 "-c", "user.name=t", "commit", "--allow-empty", "-m", "init"],
                cwd=repo, check=True, capture_output=True,
            )

        update_runtime({"active_root": str(repo_a)})

        from jetsam.core.state import build_state
        state = build_state(cwd=str(repo_b))
        assert state.repo_root.startswith(str(repo_b)), (
            "explicit cwd= should have won over active_root"
        )


class TestConfigToolViaMCP:
    """Smoke tests for the registered MCP tool."""

    @pytest.fixture(scope="class")
    def mcp(self):
        from mcp.server.fastmcp import FastMCP

        from jetsam.mcp.tools import register_tools
        server = FastMCP("test")
        register_tools(server)
        return server

    def test_config_is_registered(self, mcp):
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "config" in tool_names

    def test_signature_has_set_and_reset(self, mcp):
        tool = mcp._tool_manager._tools["config"]
        params = tool.parameters["properties"]
        assert "set" in params
        assert "reset" in params
