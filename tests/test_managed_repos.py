"""Tests for the managed repository registry (attach / clone / runs / secrets)."""

import json
import subprocess

import pytest

from app.modules.managed_repos import (
    ManagedRepoRegistry,
    RunRecorder,
    get_managed_repo_registry,
    reset_managed_repo_registry,
)


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _make_git_repo(base, name="repo"):
    repo = base / name
    repo.mkdir(parents=True)
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@test.local"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    return repo


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "neo-data"
    monkeypatch.setenv("NEO_DATA_DIR", str(d))
    reset_managed_repo_registry()
    yield d
    reset_managed_repo_registry()


class TestAttach:
    def test_attach_registers_repo_and_sets_active(self, data_dir, tmp_path):
        repo = _make_git_repo(tmp_path)
        reg = ManagedRepoRegistry(data_dir)
        record = reg.attach(str(repo))

        assert record["name"] == "repo"
        assert record["path"] == str(repo.resolve())
        assert record["default_branch"] == "main"
        assert reg.active_repo_id == record["id"]
        assert reg.get_active()["id"] == record["id"]

    def test_attach_is_idempotent(self, data_dir, tmp_path):
        repo = _make_git_repo(tmp_path)
        reg = ManagedRepoRegistry(data_dir)
        first = reg.attach(str(repo), name="custom")
        second = reg.attach(str(repo))

        assert first["id"] == second["id"]
        assert second["name"] == "custom"  # name preserved
        assert len(reg.list_repos()) == 1

    def test_attach_rejects_non_git_dir(self, data_dir, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        reg = ManagedRepoRegistry(data_dir)
        with pytest.raises(ValueError, match="Not a git repository"):
            reg.attach(str(plain))

    def test_attach_rejects_missing_path(self, data_dir, tmp_path):
        reg = ManagedRepoRegistry(data_dir)
        with pytest.raises(ValueError, match="does not exist"):
            reg.attach(str(tmp_path / "nope"))


class TestClone:
    def test_clone_local_source_registers_repo(self, data_dir, tmp_path):
        source = _make_git_repo(tmp_path, "source")
        dest = tmp_path / "clones" / "mycopy"
        reg = ManagedRepoRegistry(data_dir)

        record = reg.clone(str(source), str(dest))

        assert record["attached_existing"] is False
        assert (dest / "hello.py").exists()
        assert record["path"] == str(dest.resolve())
        assert len(reg.list_repos()) == 1

    def test_clone_attaches_existing_instead_of_recloning(self, data_dir, tmp_path):
        source = _make_git_repo(tmp_path, "source")
        dest = tmp_path / "clones" / "mycopy"
        reg = ManagedRepoRegistry(data_dir)

        first = reg.clone(str(source), str(dest))
        second = reg.clone(str(source), str(dest))

        assert second["attached_existing"] is True
        assert second["id"] == first["id"]
        assert len(reg.list_repos()) == 1

    def test_clone_refuses_nonempty_mismatched_dir(self, data_dir, tmp_path):
        source = _make_git_repo(tmp_path, "source")
        dest = tmp_path / "occupied"
        dest.mkdir()
        (dest / "file.txt").write_text("x", encoding="utf-8")
        reg = ManagedRepoRegistry(data_dir)

        with pytest.raises(ValueError, match="not empty"):
            reg.clone(str(source), str(dest))

    def test_clone_refuses_repo_with_different_remote(self, data_dir, tmp_path):
        source = _make_git_repo(tmp_path, "source")
        other = _make_git_repo(tmp_path, "other")
        dest = tmp_path / "clones" / "mycopy"
        reg = ManagedRepoRegistry(data_dir)

        reg.clone(str(other), str(dest))
        with pytest.raises(ValueError, match="different remote"):
            reg.clone(str(source), str(dest))

    def test_clone_token_never_persisted(self, data_dir, tmp_path):
        source = _make_git_repo(tmp_path, "source")
        dest = tmp_path / "clones" / "mycopy"
        reg = ManagedRepoRegistry(data_dir)

        secret = "ghp_SUPERSECRETTOKEN123"
        reg.clone(str(source), str(dest), token=secret)
        reg.record_run({"task": "t", "status": "committed"})

        for fname in ("repos.json", "runs.json"):
            content = (data_dir / fname).read_text(encoding="utf-8")
            assert secret not in content
        git_config = (dest / ".git" / "config").read_text(encoding="utf-8")
        assert secret not in git_config


class TestActiveAndPersistence:
    def test_set_active_and_restart_persistence(self, data_dir, tmp_path):
        repo_a = _make_git_repo(tmp_path, "a")
        repo_b = _make_git_repo(tmp_path, "b")
        reg = ManagedRepoRegistry(data_dir)
        rec_a = reg.attach(str(repo_a))
        rec_b = reg.attach(str(repo_b))
        reg.set_active(rec_b["id"])

        # simulate restart: new instance over the same data dir
        reg2 = ManagedRepoRegistry(data_dir)
        assert {r["id"] for r in reg2.list_repos()} == {rec_a["id"], rec_b["id"]}
        assert reg2.active_repo_id == rec_b["id"]

    def test_set_active_unknown_id_raises(self, data_dir):
        reg = ManagedRepoRegistry(data_dir)
        with pytest.raises(ValueError, match="Unknown repo id"):
            reg.set_active("nope")

    def test_mark_indexed_persists_stats(self, data_dir, tmp_path):
        repo = _make_git_repo(tmp_path)
        reg = ManagedRepoRegistry(data_dir)
        record = reg.attach(str(repo))
        reg.mark_indexed(record["id"], {"added": 3, "updated": 0, "removed": 0, "reused": 0})

        reg2 = ManagedRepoRegistry(data_dir)
        stored = reg2.get_repo(record["id"])
        assert stored["last_indexed_at"] is not None
        assert stored["last_index_stats"]["added"] == 3

    def test_ensure_default_attaches_repo_path(self, data_dir, tmp_path):
        repo = _make_git_repo(tmp_path)
        reg = ManagedRepoRegistry(data_dir)
        reg.ensure_default(str(repo))

        assert len(reg.list_repos()) == 1
        assert reg.get_active()["path"] == str(repo.resolve())
        # no-op when registry already has entries
        reg.ensure_default(str(_make_git_repo(tmp_path, "second")))
        assert len(reg.list_repos()) == 1

    def test_ensure_default_ignores_non_git_path(self, data_dir, tmp_path):
        reg = ManagedRepoRegistry(data_dir)
        reg.ensure_default(str(tmp_path))
        assert reg.list_repos() == []

    def test_singleton_uses_env_data_dir(self, data_dir, tmp_path):
        repo = _make_git_repo(tmp_path)
        reg = get_managed_repo_registry()
        assert reg is get_managed_repo_registry()
        reg.attach(str(repo))
        assert (data_dir / "repos.json").exists()


class TestRunHistory:
    def test_record_and_list_runs_newest_first(self, data_dir):
        reg = ManagedRepoRegistry(data_dir)
        reg.record_run({"task": "first", "status": "committed"})
        reg.record_run({"task": "second", "status": "blocked"})

        runs = reg.list_runs()
        assert runs[0]["task"] == "second"
        assert runs[1]["task"] == "first"

        reg2 = ManagedRepoRegistry(data_dir)
        assert len(reg2.list_runs()) == 2

    def test_run_history_is_capped(self, data_dir):
        from app.modules import managed_repos as mr
        reg = ManagedRepoRegistry(data_dir)
        for i in range(mr.MAX_RUN_HISTORY + 25):
            reg.record_run({"task": f"t{i}", "status": "committed"})
        assert len(reg.list_runs(limit=10_000)) == mr.MAX_RUN_HISTORY

    def test_run_recorder_observes_terminal_events(self, data_dir):
        reg = ManagedRepoRegistry(data_dir)
        rec = RunRecorder(reg, task="do it", repo_path=str(data_dir), model="gpt-4o")
        rec.observe({"type": "tool_end", "path": "a.py"})
        rec.observe({"type": "tool_end", "path": "a.py"})  # deduped
        rec.observe({"type": "commit", "commit_sha": "abc123",
                     "pre_run_ref": "def456"})
        rec.finalize()
        rec.finalize()  # idempotent

        runs = reg.list_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "committed"
        assert runs[0]["commit"] == "abc123"
        assert runs[0]["pre_run_ref"] == "def456"
        assert runs[0]["files"] == ["a.py"]
        assert runs[0]["model"] == "gpt-4o"
        assert runs[0]["finished_at"] is not None

    def test_run_recorder_blocked_and_error(self, data_dir):
        reg = ManagedRepoRegistry(data_dir)
        rec = RunRecorder(reg, task="x", repo_path=None)
        rec.observe({"type": "change_set_blocked", "reasons": ["bad"]})
        rec.finalize()

        rec2 = RunRecorder(reg, task="y", repo_path=None)
        rec2.observe({"type": "error", "error": "boom"})
        rec2.finalize()

        runs = reg.list_runs()
        assert runs[0]["status"] == "error"
        assert runs[0]["error"] == "boom"
        assert runs[1]["status"] == "blocked"
