"""
Tests for the git-history ingestion analyzer (app/modules/git_history.py)
and its surfacing via the context engine.
"""

import subprocess

import pytest

from app.modules.git_history import (
    get_recent_commits,
    find_relevant_commits,
    summarize_history,
)


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=str(repo), check=True, capture_output=True,
    )


def _commit(repo, path, content, message):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _commit(tmp_path, "payments.py", "def charge():\n    return 1\n",
            "feat: add payment charging")
    _commit(tmp_path, "users.py", "def create_user():\n    return 2\n",
            "feat: user creation")
    _commit(tmp_path, "payments.py", "def charge():\n    return 3\n",
            "fix: payment rounding bug")
    return tmp_path


class TestGetRecentCommits:
    def test_parses_subject_and_files(self, repo):
        commits = get_recent_commits(str(repo))
        assert len(commits) == 3
        newest = commits[0]
        assert newest["subject"] == "fix: payment rounding bug"
        assert newest["files"] == ["payments.py"]
        assert newest["short_sha"] and newest["sha"]
        assert newest["author"] == "t"

    def test_limit_is_respected(self, repo):
        commits = get_recent_commits(str(repo), limit=2)
        assert len(commits) == 2

    def test_non_git_dir_returns_empty(self, tmp_path):
        assert get_recent_commits(str(tmp_path)) == []


class TestRelevance:
    def test_keyword_match_surfaces_commit(self, repo):
        results = find_relevant_commits(str(repo), "fix the payment rounding")
        assert results
        assert results[0]["subject"] == "fix: payment rounding bug"
        assert results[0]["reason"]

    def test_path_overlap_scores_higher(self, repo):
        results = find_relevant_commits(
            str(repo), "unrelated wording", paths=["payments.py"], limit=5
        )
        assert results
        assert all("payments.py" in c["files"] for c in results)
        assert any("touches" in c["reason"] for c in results)

    def test_irrelevant_task_returns_nothing(self, repo):
        results = find_relevant_commits(
            str(repo), "kubernetes helm chart", paths=["nonexistent.go"]
        )
        assert results == []

    def test_limit_bounds_results(self, repo):
        results = find_relevant_commits(
            str(repo), "payment user", paths=["payments.py", "users.py"], limit=1
        )
        assert len(results) == 1

    def test_summary_mentions_count(self, repo):
        results = find_relevant_commits(str(repo), "payment")
        summary = summarize_history(results)
        assert "relevant commit(s)" in summary

    def test_empty_summary_for_no_commits(self):
        assert summarize_history([]) == ""


class TestContextEngineSurfacing:
    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NEO_DISABLE_EMBEDDINGS", "1")
        monkeypatch.setenv("NEO_DATA_DIR", str(tmp_path / "_neo_data"))
        from app.modules import managed_repos, repo_index
        repo_index.reset_repo_index_cache()
        managed_repos.reset_managed_repo_registry()
        yield
        repo_index.reset_repo_index_cache()
        managed_repos.reset_managed_repo_registry()

    def test_history_attached_to_context_pack(self, repo):
        from app.interactive.context_engine import ContextEngine
        from app.interactive.contracts import ChatContext

        engine = ContextEngine(str(repo))
        chat_context = ChatContext(
            current_file="payments.py",
            current_file_content="def charge():\n    return 3\n",
        )
        pack = engine.build_context_pack("fix payment rounding", chat_context)

        assert pack.recent_history is not None
        assert pack.recent_history.commits
        assert "history:" in pack.summary
