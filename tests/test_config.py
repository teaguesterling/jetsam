"""Tests for configuration loading."""

from pathlib import Path

from jetsam.config.manager import JetsamConfig, load_config


class TestLoadConfig:
    def test_defaults(self, tmp_path: Path):
        config = load_config(repo_root=str(tmp_path))
        assert config.platform == "auto"
        assert config.merge_strategy == "squash"
        assert config.auto_push is False
        assert config.ship_default == "pr"

    def test_repo_config(self, tmp_path: Path):
        config_dir = tmp_path / ".jetsam"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text(
            "platform: github\nmerge_strategy: rebase\nauto_push: true\n"
        )

        config = load_config(repo_root=str(tmp_path))
        assert config.platform == "github"
        assert config.merge_strategy == "rebase"
        assert config.auto_push is True
        # Defaults still apply for unset values
        assert config.ship_default == "pr"

    def test_invalid_yaml(self, tmp_path: Path):
        config_dir = tmp_path / ".jetsam"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("not: [valid: yaml: {{")

        # Should not raise, just use defaults
        config = load_config(repo_root=str(tmp_path))
        assert config.platform == "auto"

    def test_no_repo_root(self):
        config = load_config(repo_root=None)
        assert isinstance(config, JetsamConfig)

    def test_unknown_keys_ignored(self, tmp_path: Path):
        config_dir = tmp_path / ".jetsam"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text(
            "platform: github\nunknown_key: value\n"
        )

        config = load_config(repo_root=str(tmp_path))
        assert config.platform == "github"
        assert not hasattr(config, "unknown_key")
