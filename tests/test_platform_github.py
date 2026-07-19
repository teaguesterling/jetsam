"""Tests for GitHub platform adapter.

These tests mock the gh CLI to avoid requiring authentication.
"""

from unittest.mock import patch

import pytest

from jetsam.platforms.base import CheckResult, IssueDetails, PRDetails
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

    def test_mergeable_true(self):
        pr = _parse_pr({"number": 1, "state": "open", "mergeable": "MERGEABLE"})
        assert pr.mergeable is True
        assert pr.mergeable_state == "mergeable"

    def test_mergeable_conflicting(self):
        pr = _parse_pr({"number": 1, "state": "open", "mergeable": "CONFLICTING"})
        assert pr.mergeable is False
        assert pr.mergeable_state == "conflicting"

    def test_mergeable_unknown(self):
        # gh reports UNKNOWN while GitHub is still computing mergeability
        pr = _parse_pr({"number": 1, "state": "open", "mergeable": "UNKNOWN"})
        assert pr.mergeable is False
        assert pr.mergeable_state == "unknown"

    def test_mergeable_missing(self):
        pr = _parse_pr({"number": 1, "state": "open"})
        assert pr.mergeable is False
        assert pr.mergeable_state == "unknown"

    def test_extra_api_fields_ignored(self):
        # gh may return fields we don't request/declare; they must not crash
        pr = _parse_pr({
            "number": 1,
            "state": "open",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "someFutureField": {"nested": True},
        })
        assert pr.number == 1
        assert pr.mergeable is True


class TestFieldTolerance:
    """Unknown/new fields must never crash model construction.

    Regression for: PRDetails.__init__() got an unexpected keyword argument
    'mergeable_state' — raised when a newer adapter passed a field a loaded
    older model didn't declare. from_fields() drops unknown kwargs.
    """

    def test_prdetails_tolerates_unknown_fields(self):
        pr = PRDetails.from_fields(
            number=7,
            state="open",
            title="t",
            mergeable_state="mergeable",
            made_up_future_field="surprise",
        )
        assert pr.number == 7
        assert pr.mergeable_state == "mergeable"
        assert not hasattr(pr, "made_up_future_field")

    def test_prdetails_from_api_dict_with_extras(self):
        data = {"number": 3, "state": "open", "title": "x",
                "mergeable_state": "conflicting", "brand_new_field": 123}
        pr = PRDetails.from_fields(**data)
        assert pr.number == 3
        assert pr.mergeable_state == "conflicting"

    def test_issuedetails_tolerates_unknown_fields(self):
        issue = IssueDetails.from_fields(
            number=9, title="i", state="open", reaction_summary={"+1": 2},
        )
        assert issue.number == 9

    def test_checkresult_tolerates_unknown_fields(self):
        check = CheckResult.from_fields(
            name="ci", status="pass", started_at="2026-01-01T00:00:00Z",
        )
        assert check.name == "ci"
        assert check.status == "pass"


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
        # The documented hyphenated spelling is normalized to the space form
        # gh actually accepts ("not planned"); passing "not-planned" through
        # verbatim made gh reject the call (issue #19 follow-up).
        platform = GitHubPlatform()
        with patch.object(platform, "_run_gh", return_value=(True, "", "")) as mock:
            platform.issue_close(42, reason="not-planned")
            close_call = mock.call_args_list[-1]
            assert "not planned" in close_call[0][0]
            assert "not-planned" not in close_call[0][0]

    def test_close_failure(self):
        platform = GitHubPlatform()
        with (
            patch.object(platform, "_run_gh", return_value=(False, "", "not found")),
            pytest.raises(PlatformError),
        ):
            platform.issue_close(999)
