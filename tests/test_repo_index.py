"""
Tests for the persistent RepoIndex (Phase B).
Embeddings are disabled via NEO_DISABLE_EMBEDDINGS for deterministic keyword
behavior; the semantic path is covered with a fake embedding model.
"""

import importlib
import json
import time
from pathlib import Path

import pytest

from app.modules.repo_index import RepoIndex


def _live_module():
    """Resolve app.modules.repo_index at run time.

    Some suites (e.g. tests/test_api.py) wipe app.* from sys.modules, after
    which this test module's collection-time imports refer to a stale module
    object. Production code imports repo_index at call time, so anything that
    must share state with it has to resolve the module the same way.
    """
    return importlib.import_module("app.modules.repo_index")


@pytest.fixture(autouse=True)
def _isolated_index(monkeypatch):
    """Disable real embeddings and clear the shared cache around each test."""
    monkeypatch.setenv("NEO_DISABLE_EMBEDDINGS", "1")
    _live_module().reset_repo_index_cache()
    yield
    _live_module().reset_repo_index_cache()


def _make_repo(tmp_path):
    (tmp_path / "payments.py").write_text(
        "def compute_payment_schedule(amount):\n"
        "    '''Compute the payment schedule.'''\n"
        "    return amount * 12\n"
    )
    (tmp_path / "users.py").write_text(
        "def create_user(name):\n    return {'name': name}\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_payments.py").write_text(
        "def test_payment():\n    assert True\n"
    )
    (tmp_path / "conftest.py").write_text("import pytest\n")
    return tmp_path


class TestPersistence:
    def test_first_run_builds_index_on_disk(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        stats = index.refresh()

        assert stats["added"] == 4
        assert stats["removed"] == 0
        assert (repo / ".neo" / "index" / "manifest.json").exists()
        assert (repo / ".neo" / "index" / "chunks.json").exists()
        manifest = json.loads(
            (repo / ".neo" / "index" / "manifest.json").read_text()
        )
        assert "payments.py" in manifest["files"]

    def test_second_run_reuses_existing_data(self, tmp_path):
        repo = _make_repo(tmp_path)
        RepoIndex(str(repo)).refresh()

        # Fresh instance simulates a new process loading persisted data
        index2 = RepoIndex(str(repo))
        stats = index2.refresh()

        assert stats["added"] == 0
        assert stats["updated"] == 0
        assert stats["reused"] == 4

    def test_changed_file_is_reindexed(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        index.refresh()

        (repo / "users.py").write_text(
            "def create_user(name, email):\n"
            "    return {'name': name, 'email': email}\n"
        )
        stats = index.refresh()

        assert stats["updated"] == 1
        assert stats["added"] == 0
        assert stats["reused"] == 3

    def test_deleted_file_is_removed_from_index(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        index.refresh()

        (repo / "users.py").unlink()
        stats = index.refresh()

        assert stats["removed"] == 1
        assert index.get_file_metadata("users.py") is None
        paths = [r["path"] for r in index.search("create user", k=10)]
        assert "users.py" not in paths

    def test_neo_guidelines_file_disables_persistence(self, tmp_path):
        repo = _make_repo(tmp_path)
        (repo / ".neo").write_text("Always write tests.\n")

        index = RepoIndex(str(repo))
        stats = index.refresh()

        assert index.persist_dir is None
        assert stats["added"] == 4          # in-memory index still works
        assert not (repo / ".neo" / "index").exists()


class TestSearchAndMetadata:
    def test_keyword_search_surfaces_expected_files(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))

        results = index.search("update the payments schedule logic", k=5)

        assert results
        assert results[0]["path"] in ("payments.py", "tests/test_payments.py")
        assert "keyword match" in results[0]["reason"]
        assert any(r["path"] == "payments.py" for r in results)

    def test_search_results_are_bounded(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        assert len(index.search("payments user test", k=2)) <= 2

    def test_file_metadata_flags(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        index.refresh()

        payments = index.get_file_metadata("payments.py")
        assert payments["language"] == "python"
        assert payments["is_test"] is False

        test_meta = index.get_file_metadata("tests/test_payments.py")
        assert test_meta["is_test"] is True

        conftest = index.get_file_metadata("conftest.py")
        assert conftest["is_convention"] is True

    def test_summarize(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        summary = index.summarize()

        assert summary["total_files"] == 4
        assert summary["languages"]["python"] == 4
        assert summary["test_files"] == 1
        assert summary["embeddings_available"] is False


class _FakeEmbedModel:
    """Deterministic stand-in for sentence-transformers."""

    def __init__(self):
        self.encode_calls: list[list[str]] = []

    def encode(self, texts, **kwargs):
        import numpy as np
        self.encode_calls.append(list(texts))
        out = []
        for t in texts:
            v = np.zeros(2, dtype="float32")
            v[0 if "payment" in t.lower() else 1] = 1.0
            out.append(v)
        return np.asarray(out)


def _with_fake_embedder(index: RepoIndex) -> _FakeEmbedModel:
    model = _FakeEmbedModel()
    index._embed_model = model
    index._embed_attempted = True
    return model


class TestSemanticPath:
    def test_semantic_search_with_fake_embedder(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        _with_fake_embedder(index)

        results = index.search("payment", k=3)

        assert results
        assert results[0]["path"] in ("payments.py", "tests/test_payments.py")
        assert "semantic match" in results[0]["reason"]
        assert results[0]["score"] == pytest.approx(1.0)

    def test_incremental_refresh_only_embeds_changed_files(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        model = _with_fake_embedder(index)
        index.refresh()
        first_build_chunks = sum(len(c) for c in model.encode_calls)

        (repo / "users.py").write_text("def create_user(n, e):\n    return n\n")
        model.encode_calls.clear()
        index.refresh()

        re_embedded = sum(len(c) for c in model.encode_calls)
        assert re_embedded == 1            # only users.py's single chunk
        assert re_embedded < first_build_chunks


class TestBackgroundWatcher:
    def test_watcher_picks_up_new_file(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        index.refresh()
        assert index.get_file_metadata("late.py") is None

        assert index.start_watching(interval=0.05) is True
        try:
            (repo / "late.py").write_text("def added():\n    return 1\n")
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if index.get_file_metadata("late.py") is not None:
                    break
                time.sleep(0.05)
            assert index.get_file_metadata("late.py") is not None
        finally:
            index.stop_watching()
        assert index.is_watching is False

    def test_start_watching_is_idempotent(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        try:
            assert index.start_watching(interval=0.1) is True
            assert index.start_watching(interval=0.1) is False
            assert index.is_watching is True
        finally:
            index.stop_watching()

    def test_stop_watching_joins_thread(self, tmp_path):
        repo = _make_repo(tmp_path)
        index = RepoIndex(str(repo))
        index.start_watching(interval=0.1)
        index.stop_watching()
        assert index.is_watching is False

    def test_reset_cache_stops_watchers(self, tmp_path):
        rim = _live_module()
        repo = _make_repo(tmp_path)
        index = rim.get_repo_index(str(repo))
        index.start_watching(interval=0.1)
        assert index.is_watching is True

        rim.reset_repo_index_cache()
        assert index.is_watching is False


class TestSharedInstance:
    def test_get_repo_index_returns_same_instance(self, tmp_path):
        rim = _live_module()
        repo = _make_repo(tmp_path)
        assert rim.get_repo_index(str(repo)) is rim.get_repo_index(str(repo))

    def test_context_engine_and_tool_executor_share_index(self, tmp_path):
        from app.interactive.context_engine import ContextEngine
        from app.interactive.tools import ToolExecutor

        rim = _live_module()
        repo = _make_repo(tmp_path)

        engine = ContextEngine(str(repo))
        engine.build_context_pack("update the payments schedule")
        executor = ToolExecutor(str(repo))
        out = executor._semantic_search({"query": "payments schedule"})

        # Both consumers resolved a single shared index through get_repo_index:
        # exactly one cache entry, and it is the instance the cache hands out.
        key = str(Path(repo).resolve())
        assert list(rim._INDEX_CACHE.keys()) == [key]
        assert rim.get_repo_index(str(repo)) is rim._INDEX_CACHE[key]
        assert "payments.py" in out
