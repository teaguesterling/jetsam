"""Tests for GitHub platform adapter.

These tests mock the gh CLI to avoid requiring authentication.
"""

from unittest.mock import patch

import pytest

from jetsam.platforms.github import (
    GitHubPlatform,
    PlatformError,
    _normalize_check_status,
    _parse_pr,
)


class TestParsepr:
    def test_basic(self):
        data = {
            "number": 42,
            "state": "OPEN",
            "title": "Fix parser",
            "body": "Fixes the parser bug",
            "url": "https://github.com/user/repo/pull/42",
            "baseRefName": "main",
            "headRefName": "fix-parser",
            "isDraft": False,
            "labels": [{"name": "bug"}],
        }
        pr = _parse_pr(data)
        assert pr.number == 42
        assert pr.state == "open"
        assert pr.title == "Fix parser"
        assert pr.base == "main"
        assert pr.labels == ["bug"]

    def test_empty_labels(self):
        data = {"number": 1, "state": "open", "labels": []}
        pr = _parse_pr(data)
        assert pr.labels == []


class TestNormalizeCheckStatus:
    def test_pass(self):
        assert _normalize_check_status("SUCCESS") == "pass"
        assert _normalize_check_status("pass") == "pass"

    def test_fail(self):
        assert _normalize_check_status("FAILURE") == "fail"
        assert _normalize_check_status("error") == "fail"

    def test_pending(self):
        assert _normalize_check_status("PENDING") == "pending"
        assert _normalize_check_status("in_progress") == "pending"

    def test_neutral(self):
        assert _normalize_check_status("neutral") == "neutral"
        assert _normalize_check_status("skipped") == "neutral"


class TestGitHubPlatform:
    def test_pr_for_branch_not_found(self):
        """When gh returns an error, pr_for_branch returns None."""
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", return_value=(False, "no PR")):
            result = platform.pr_for_branch("no-pr-branch")
            assert result is None

    def test_pr_for_branch_found(self):
        platform = GitHubPlatform()
        mock_data = {
            "number": 10,
            "state": "OPEN",
            "title": "Feature",
            "body": "",
            "url": "https://github.com/u/r/pull/10",
            "baseRefName": "main",
            "headRefName": "feature",
            "isDraft": False,
            "labels": [],
        }
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            pr = platform.pr_for_branch("feature")
            assert pr is not None
            assert pr.number == 10

    def test_pr_list_empty(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", return_value=(True, [])):
            prs = platform.pr_list()
            assert prs == []

    def test_pr_list(self):
        platform = GitHubPlatform()
        mock_data = [
            {"number": 1, "state": "open", "title": "PR 1", "url": "", "baseRefName": "main",
             "headRefName": "a", "isDraft": False, "labels": []},
            {"number": 2, "state": "open", "title": "PR 2", "url": "", "baseRefName": "main",
             "headRefName": "b", "isDraft": True, "labels": []},
        ]
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            prs = platform.pr_list()
            assert len(prs) == 2
            assert prs[1].draft is True

    def test_pr_checks(self):
        platform = GitHubPlatform()
        mock_data = [
            {"name": "CI", "state": "SUCCESS", "detailsUrl": "https://ci.example.com"},
            {"name": "Lint", "state": "FAILURE", "detailsUrl": ""},
        ]
        with patch.object(platform, "_run_gh_json", return_value=(True, mock_data)):
            checks = platform.pr_checks(42)
            assert len(checks) == 2
            assert checks[0].status == "pass"
            assert checks[1].status == "fail"


class TestPrComment:
    def test_success(self):
        platform = GitHubPlatform()
        with patch.object(
            platform,
            "_run_gh",
            return_value=(True, "https://github.com/u/r/pull/42#issuecomment-123", ""),
        ):
            result = platform.pr_comment(42, "Looks good!")
            assert result["number"] == "42"
            assert "url" in result

    def test_failure(self):
        platform = GitHubPlatform()
        with (
            patch.object(platform, "_run_gh", return_value=(False, "", "not found")),
            pytest.raises(PlatformError),
        ):
            platform.pr_comment(42, "comment")


class TestPrReview:
    def test_approve(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")):
            result = platform.pr_review(42, "", "approve")
            assert result["event"] == "approve"

    def test_request_changes(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")):
            result = platform.pr_review(42, "Fix the bug", "request-changes")
            assert result["event"] == "request-changes"

    def test_failure(self):
        platform = GitHubPlatform()
        with (
            patch.object(platform, "_run_gh", return_value=(False, "", "error")),
            pytest.raises(PlatformError),
        ):
            platform.pr_review(42, "comment", "approve")


class TestPrComments:
    def test_returns_merged_comments(self):
        platform = GitHubPlatform()
        issue_comments = [
            {"user": {"login": "alice"}, "body": "Nice", "created_at": "2026-01-01T00:00:00Z"},
        ]
        review_comments = [
            {
                "user": {"login": "bob"},
                "body": "LGTM",
                "submitted_at": "2026-01-02T00:00:00Z",
                "state": "APPROVED",
            },
        ]
        with patch.object(platform, "_run_gh_json", side_effect=[
            (True, issue_comments),
            (True, review_comments),
        ]):
            result = platform.pr_comments(42)
            assert len(result) == 2
            assert result[0]["author"] == "alice"
            assert result[0]["type"] == "comment"
            assert result[1]["author"] == "bob"
            assert result[1]["type"] == "review"

    def test_empty(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", side_effect=[
            (True, []),
            (True, []),
        ]):
            result = platform.pr_comments(42)
            assert result == []

    def test_api_failure_returns_empty(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh_json", side_effect=[
            (False, "error"),
            (False, "error"),
        ]):
            result = platform.pr_comments(42)
            assert result == []


class TestIssueClose:
    def test_close_simple(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")):
            result = platform.issue_close(42)
            assert result["number"] == "42"
            assert result["state"] == "closed"

    def test_close_with_comment(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")) as mock:
            result = platform.issue_close(42, comment="Fixed in #10")
            assert mock.call_count == 2
            assert result["state"] == "closed"

    def test_close_not_planned(self):
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")) as mock:
            platform.issue_close(42, reason="not-planned")
            close_call = mock.call_args_list[-1]
            assert "not-planned" in close_call[0][0]

    def test_close_failure(self):
        platform = GitHubPlatform()
        with (
            patch.object(platform, "_run_gh", return_value=(False, "", "not found")),
            pytest.raises(PlatformError),
        ):
            platform.issue_close(999)
