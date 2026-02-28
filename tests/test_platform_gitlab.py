"""Tests for GitLab platform adapter."""

from jetsam.platforms.gitlab import (
    _normalize_pipeline_status,
    _parse_gl_issue,
    _parse_mr,
)


class TestParseMR:
    def test_basic(self):
        data = {
            "iid": 42,
            "title": "Fix parser",
            "state": "opened",
            "description": "Fixes a bug",
            "web_url": "https://gitlab.com/user/repo/-/merge_requests/42",
            "target_branch": "main",
            "source_branch": "fix-parser",
            "draft": False,
            "labels": ["bug"],
        }
        pr = _parse_mr(data)
        assert pr.number == 42
        assert pr.state == "open"  # "opened" -> "open"
        assert pr.title == "Fix parser"
        assert pr.body == "Fixes a bug"
        assert pr.base == "main"
        assert pr.head == "fix-parser"
        assert pr.draft is False
        assert pr.labels == ["bug"]

    def test_merged_state(self):
        data = {"iid": 1, "state": "merged", "title": "done"}
        pr = _parse_mr(data)
        assert pr.state == "merged"

    def test_closed_state(self):
        data = {"iid": 1, "state": "closed", "title": "wontfix"}
        pr = _parse_mr(data)
        assert pr.state == "closed"

    def test_draft_via_wip(self):
        data = {"iid": 1, "state": "opened", "title": "WIP: feature",
                "draft": False, "work_in_progress": True}
        pr = _parse_mr(data)
        assert pr.draft is True

    def test_missing_fields(self):
        data = {"iid": 5, "state": "opened"}
        pr = _parse_mr(data)
        assert pr.number == 5
        assert pr.title == ""
        assert pr.body == ""
        assert pr.labels == []

    def test_fallback_number_field(self):
        data = {"number": 10, "state": "opened", "title": "test"}
        pr = _parse_mr(data)
        assert pr.number == 10


class TestParseGLIssue:
    def test_basic(self):
        data = {
            "iid": 7,
            "title": "Bug report",
            "state": "opened",
            "description": "Details here",
            "web_url": "https://gitlab.com/user/repo/-/issues/7",
            "labels": ["bug", "critical"],
            "assignees": [{"username": "dev1"}, {"username": "dev2"}],
        }
        issue = _parse_gl_issue(data)
        assert issue.number == 7
        assert issue.title == "Bug report"
        assert issue.state == "open"
        assert issue.body == "Details here"
        assert issue.labels == ["bug", "critical"]
        assert issue.assignees == ["dev1", "dev2"]

    def test_closed_state(self):
        data = {"iid": 1, "state": "closed", "title": "done"}
        issue = _parse_gl_issue(data)
        assert issue.state == "closed"

    def test_missing_fields(self):
        data = {"iid": 3, "state": "opened"}
        issue = _parse_gl_issue(data)
        assert issue.number == 3
        assert issue.title == ""
        assert issue.labels == []
        assert issue.assignees == []


class TestNormalizePipelineStatus:
    def test_success(self):
        assert _normalize_pipeline_status("success") == "pass"
        assert _normalize_pipeline_status("passed") == "pass"

    def test_failure(self):
        assert _normalize_pipeline_status("failed") == "fail"
        assert _normalize_pipeline_status("canceled") == "fail"

    def test_pending(self):
        assert _normalize_pipeline_status("pending") == "pending"
        assert _normalize_pipeline_status("running") == "pending"
        assert _normalize_pipeline_status("created") == "pending"

    def test_neutral(self):
        assert _normalize_pipeline_status("skipped") == "neutral"
        assert _normalize_pipeline_status("unknown") == "neutral"
