"""Tests for git output parsers."""

from jetsam.git.parsers import (
    parse_branches,
    parse_diff_numstat,
    parse_diff_stat,
    parse_log,
    parse_remote_url,
    parse_stash_list,
    parse_status,
)


class TestParseStatus:
    def test_clean_repo(self):
        output = "# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n"
        result = parse_status(output)
        assert result.branch.head == "main"
        assert result.branch.upstream == "origin/main"
        assert result.branch.ahead == 0
        assert result.branch.behind == 0
        assert not result.dirty

    def test_dirty_repo(self):
        output = (
            "# branch.head feature\n"
            "# branch.upstream origin/feature\n"
            "# branch.ab +2 -1\n"
            "1 M. N... 100644 100644 100644 abc123 def456 src/main.py\n"
            "1 .M N... 100644 100644 100644 abc123 def456 src/utils.py\n"
            "? scratch.txt\n"
        )
        result = parse_status(output)
        assert result.branch.head == "feature"
        assert result.branch.ahead == 2
        assert result.branch.behind == 1
        assert result.dirty
        assert len(result.staged) == 1
        assert result.staged[0].path == "src/main.py"
        assert result.staged[0].index_status == "M"
        assert len(result.unstaged) == 1
        assert result.unstaged[0].path == "src/utils.py"
        assert len(result.untracked) == 1
        assert result.untracked[0] == "scratch.txt"

    def test_rename(self):
        output = (
            "# branch.head main\n"
            "2 R. N... 100644 100644 100644 abc123 def456 R100 new.py\told.py\n"
        )
        result = parse_status(output)
        assert len(result.staged) == 1
        assert result.staged[0].path == "new.py"
        assert result.staged[0].original_path == "old.py"
        assert result.staged[0].index_status == "R"

    def test_no_upstream(self):
        output = "# branch.head new-branch\n"
        result = parse_status(output)
        assert result.branch.head == "new-branch"
        assert result.branch.upstream is None
        assert result.branch.ahead == 0
        assert result.branch.behind == 0

    def test_detached_head(self):
        output = "# branch.head (detached)\n"
        result = parse_status(output)
        assert result.branch.head == "(detached)"

    def test_added_and_modified(self):
        output = (
            "# branch.head main\n"
            "1 AM N... 100644 100644 100644 abc123 def456 new_file.py\n"
        )
        result = parse_status(output)
        assert len(result.staged) == 1
        assert result.staged[0].index_status == "A"
        assert len(result.unstaged) == 1
        assert result.unstaged[0].worktree_status == "M"


class TestParseLog:
    def test_basic(self):
        output = "abc123full\x00abc123\x00Alice\x002024-01-15T10:30:00+00:00\x00fix parser bug\n"
        entries = parse_log(output)
        assert len(entries) == 1
        assert entries[0].sha == "abc123full"
        assert entries[0].short_sha == "abc123"
        assert entries[0].author == "Alice"
        assert entries[0].message == "fix parser bug"

    def test_multiple(self):
        output = (
            "aaa\x00aa\x00Alice\x002024-01-15\x00first\n"
            "bbb\x00bb\x00Bob\x002024-01-14\x00second\n"
        )
        entries = parse_log(output)
        assert len(entries) == 2
        assert entries[0].message == "first"
        assert entries[1].message == "second"

    def test_empty(self):
        assert parse_log("") == []
        assert parse_log("\n") == []


class TestParseDiffStat:
    def test_basic(self):
        output = (
            " src/main.py | 10 ++++------\n"
            " src/util.py |  3 +++\n"
            " 2 files changed, 7 insertions(+), 6 deletions(-)\n"
        )
        stat = parse_diff_stat(output)
        assert stat.files_changed == 2
        assert stat.insertions == 7
        assert stat.deletions == 6
        assert len(stat.file_stats) == 2

    def test_insertions_only(self):
        output = " 1 file changed, 5 insertions(+)\n"
        stat = parse_diff_stat(output)
        assert stat.files_changed == 1
        assert stat.insertions == 5
        assert stat.deletions == 0

    def test_deletions_only(self):
        output = " 1 file changed, 3 deletions(-)\n"
        stat = parse_diff_stat(output)
        assert stat.files_changed == 1
        assert stat.insertions == 0
        assert stat.deletions == 3


class TestParseDiffNumstat:
    def test_basic(self):
        output = "5\t3\tsrc/main.py\n2\t0\tsrc/new.py\n"
        stat = parse_diff_numstat(output)
        assert stat.files_changed == 2
        assert stat.insertions == 7
        assert stat.deletions == 3
        assert stat.file_stats[0].path == "src/main.py"
        assert stat.file_stats[0].insertions == 5
        assert stat.file_stats[0].deletions == 3

    def test_binary(self):
        output = "-\t-\timage.png\n"
        stat = parse_diff_numstat(output)
        assert stat.files_changed == 1
        assert stat.file_stats[0].insertions == 0
        assert stat.file_stats[0].deletions == 0


class TestParseBranches:
    def test_basic(self):
        output = (
            "* main       abc1234 [origin/main] latest commit\n"
            "  feature    def5678 [origin/feature] wip\n"
            "  no-remote  ghi9012 some work\n"
        )
        branches = parse_branches(output)
        assert len(branches) == 3
        assert branches[0].name == "main"
        assert branches[0].is_current
        assert branches[0].upstream == "origin/main"
        assert branches[1].name == "feature"
        assert not branches[1].is_current
        assert branches[2].upstream is None


class TestParseStashList:
    def test_empty(self):
        assert parse_stash_list("") == 0

    def test_some(self):
        output = "stash@{0}: WIP on main: abc1234 msg\nstash@{1}: WIP on main: def5678 msg2\n"
        assert parse_stash_list(output) == 2


class TestParseRemoteUrl:
    def test_github_ssh(self):
        platform, path = parse_remote_url("git@github.com:user/repo.git")
        assert platform == "github"
        assert path == "user/repo"

    def test_github_https(self):
        platform, path = parse_remote_url("https://github.com/user/repo.git")
        assert platform == "github"
        assert path == "user/repo"

    def test_github_https_no_git(self):
        platform, path = parse_remote_url("https://github.com/user/repo")
        assert platform == "github"
        assert path == "user/repo"

    def test_gitlab_ssh(self):
        platform, path = parse_remote_url("git@gitlab.com:org/project.git")
        assert platform == "gitlab"
        assert path == "org/project"

    def test_unknown(self):
        platform, _path = parse_remote_url("https://example.com/repo.git")
        assert platform == "unknown"

    def test_self_hosted_gitlab(self):
        platform, path = parse_remote_url("git@gitlab.mycompany.com:team/project.git")
        assert platform == "gitlab"
        assert path == "team/project"
