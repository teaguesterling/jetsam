"""Tests for output formatting."""

import json

from jetsam.core.output import (
    JetsamError,
    format_human_log,
    format_human_status,
    format_json,
)


class TestJetsamError:
    def test_to_dict(self):
        err = JetsamError(
            error="branch_behind",
            message="Branch is 2 commits behind main",
            suggested_action="sync",
            recoverable=True,
        )
        d = err.to_dict()
        assert d["error"] == "branch_behind"
        assert d["suggested_action"] == "sync"

    def test_format_human(self):
        err = JetsamError(
            error="branch_behind",
            message="Branch is 2 commits behind main",
            suggested_action="sync",
        )
        text = err.format_human()
        assert "\u2717" in text
        assert "sync" in text


class TestFormatJson:
    def test_dict(self):
        result = format_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_dataclass(self):
        err = JetsamError(error="test", message="test msg")
        result = format_json(err)
        parsed = json.loads(result)
        assert parsed["error"] == "test"

    def test_to_dict_method(self):
        err = JetsamError(error="test", message="msg", suggested_action=None)
        result = format_json(err)
        parsed = json.loads(result)
        assert "suggested_action" not in parsed


class TestFormatHumanStatus:
    def test_clean(self):
        state = {
            "branch": "main",
            "upstream": "origin/main",
            "ahead": 0,
            "behind": 0,
            "staged": [],
            "unstaged": [],
            "untracked": [],
            "stash_count": 0,
        }
        text = format_human_status(state)
        assert "main" in text
        assert "Clean" in text

    def test_dirty(self):
        state = {
            "branch": "feature",
            "upstream": "origin/feature",
            "ahead": 2,
            "behind": 1,
            "staged": ["src/main.py"],
            "unstaged": ["src/utils.py"],
            "untracked": ["scratch.txt"],
            "stash_count": 0,
        }
        text = format_human_status(state)
        assert "feature" in text
        assert "\u2191" in text  # ahead arrow
        assert "\u2193" in text  # behind arrow
        assert "src/main.py" in text
        assert "scratch.txt" in text


class TestFormatHumanLog:
    def test_basic(self):
        entries = [
            {"short_sha": "abc1234", "message": "fix bug", "author": "Alice"},
            {"short_sha": "def5678", "message": "add feature", "author": "Bob"},
        ]
        text = format_human_log(entries)
        assert "abc1234" in text
        assert "fix bug" in text
        assert "Alice" in text
