"""
Tests for the Phase C verifier: system-controlled verification + bounded repair.
"""

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.contracts import TestResult
from app.interactive.change_set import ChangeSet


def _collect(agen):
    async def go():
        return [e async for e in agen]
    return asyncio.run(go())


def _v_mod():
    """Run-time import — immune to the sys.modules wipe in test_api.py."""
    import app.interactive.verifier as v_mod
    return v_mod


def _script_checks(verifier, results):
    """Replace run_checks with a scripted sequence of CheckResults."""
    seq = list(results)
    verifier.run_checks = lambda change_set=None: seq.pop(0)


PASS_CMD = 'python -c "import sys; sys.exit(0)"'
FAIL_CMD = 'python -c "import sys; sys.exit(3)"'


# ── check selection + execution ───────────────────────────────────────────────

class TestRunChecks:
    def test_checkpoint_cmd_pass(self, tmp_path):
        v = _v_mod().Verifier(str(tmp_path), checkpoint_cmd=PASS_CMD)
        result = v.run_checks(None)
        assert result.passed is True
        assert result.checks_run == [PASS_CMD]

    def test_checkpoint_cmd_fail(self, tmp_path):
        v = _v_mod().Verifier(str(tmp_path), checkpoint_cmd=FAIL_CMD)
        result = v.run_checks(None)
        assert result.passed is False
        assert result.checks_run == [FAIL_CMD]

    def test_targeted_tests_from_changed_files(self, tmp_path, monkeypatch):
        v_mod = _v_mod()
        (tmp_path / "tests").mkdir()
        (tmp_path / "mod.py").write_text("x = 1\n")
        (tmp_path / "tests" / "test_mod.py").write_text("def test_x(): pass\n")

        captured = {}

        def fake_run_tests(repo_path, test_command=None, timeout=300):
            captured["cmd"] = test_command
            return TestResult(passed=True, output="ok", duration_seconds=0.0)

        monkeypatch.setattr(v_mod, "run_tests", fake_run_tests)

        cs = ChangeSet()
        cs.record("mod.py", "x = 1\n", "x = 2\n")
        result = v_mod.Verifier(str(tmp_path)).run_checks(cs)

        assert result.passed is True
        assert captured["cmd"].startswith("python -m pytest ")
        assert "tests/test_mod.py" in captured["cmd"]

    def test_changed_test_file_is_its_own_target(self, tmp_path, monkeypatch):
        v_mod = _v_mod()
        (tmp_path / "test_thing.py").write_text("def test_t(): pass\n")

        captured = {}

        def fake_run_tests(repo_path, test_command=None, timeout=300):
            captured["cmd"] = test_command
            return TestResult(passed=True, output="ok", duration_seconds=0.0)

        monkeypatch.setattr(v_mod, "run_tests", fake_run_tests)

        cs = ChangeSet()
        cs.record("test_thing.py", "", "def test_t(): pass\n", existed_before=False)
        v_mod.Verifier(str(tmp_path)).run_checks(cs)

        assert "test_thing.py" in captured["cmd"]

    def test_no_detectable_checks_is_safe_pass(self, tmp_path):
        cs = ChangeSet()
        cs.record("notes.txt", "a\n", "b\n")
        result = _v_mod().Verifier(str(tmp_path)).run_checks(cs)
        assert result.passed is True
        assert result.checks_run == []

    def test_fallback_to_auto_detection(self, tmp_path, monkeypatch):
        v_mod = _v_mod()

        def fake_run_tests(repo_path, test_command=None, timeout=300):
            assert test_command is None
            return TestResult(passed=True, output="2 passed", duration_seconds=0.1)

        monkeypatch.setattr(v_mod, "run_tests", fake_run_tests)
        cs = ChangeSet()
        cs.record("mod.py", "x = 1\n", "x = 2\n")  # no matching test file
        result = v_mod.Verifier(str(tmp_path)).run_checks(cs)
        assert result.passed is True
        assert result.checks_run == ["(auto-detected test command)"]


class TestSyntaxCheckFallback:
    """No project tests → broken code is still caught (and thus auto-reverted)."""

    def test_broken_python_fails(self, tmp_path):
        (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("broken.py", "", "def f(:\n", existed_before=False)
        result = _v_mod().Verifier(str(tmp_path))._syntax_check(cs)
        assert result.passed is False
        assert "syntax: python (py_compile)" in result.checks_run
        assert result.failure_summary

    def test_valid_python_passes(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("ok.py", "", "x = 1\n", existed_before=False)
        result = _v_mod().Verifier(str(tmp_path))._syntax_check(cs)
        assert result.passed is True
        assert "syntax: python (py_compile)" in result.checks_run

    def test_broken_json_fails(self, tmp_path):
        (tmp_path / "data.json").write_text("{bad json", encoding="utf-8")
        cs = ChangeSet()
        cs.record("data.json", "", "{bad json", existed_before=False)
        result = _v_mod().Verifier(str(tmp_path))._syntax_check(cs)
        assert result.passed is False
        assert "syntax: json" in result.checks_run

    def test_unsupported_file_is_safe_pass(self, tmp_path):
        (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("notes.txt", "", "hello\n", existed_before=False)
        result = _v_mod().Verifier(str(tmp_path))._syntax_check(cs)
        assert result.passed is True
        assert result.checks_run == []

    def test_deleted_file_is_not_checked(self, tmp_path):
        # A deleted .py must not be syntax-checked (it's gone from disk).
        cs = ChangeSet()
        cs.record_delete("gone.py", "def f(:\n")
        result = _v_mod().Verifier(str(tmp_path))._syntax_check(cs)
        assert result.passed is True
        assert result.checks_run == []

    def test_run_checks_routes_to_syntax_when_no_tests(self, tmp_path, monkeypatch):
        v_mod = _v_mod()

        def fake_run_tests(repo_path, test_command=None, timeout=300):
            return TestResult(
                passed=False, output="No test command configured",
                duration_seconds=0.0,
            )

        monkeypatch.setattr(v_mod, "run_tests", fake_run_tests)
        (tmp_path / "broken.py").write_text("def f(:\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("broken.py", "", "def f(:\n", existed_before=False)
        result = v_mod.Verifier(str(tmp_path)).run_checks(cs)
        assert result.passed is False
        assert "syntax: python (py_compile)" in result.checks_run


class TestSummarizeFailure:
    def test_keeps_signal_lines_and_caps_length(self):
        v_mod = _v_mod()
        noise = "\n".join(f"line {i}" for i in range(200))
        output = noise + "\nFAILED tests/test_x.py::test_a - assert 1 == 2\n"
        summary = v_mod._summarize_failure(output)
        assert "FAILED tests/test_x.py::test_a" in summary
        assert len(summary) <= 1500


# ── verify_and_repair: events + bounded repair ───────────────────────────────

class _RepairAgent:
    """AgentLoop stand-in for repair attempts: stages one fix file."""
    instances = 0

    def __init__(self, model_router=None, repo_path=None, **kwargs):
        type(self).instances += 1

    async def run(self, **kwargs):
        cs = ChangeSet()
        cs.record("fix.py", "", "fixed\n", existed_before=False)
        return SimpleNamespace(
            success=True, summary="repaired", tool_calls=[],
            files_written=["fix.py"], error=None, change_set=cs,
        )


class TestVerifyAndRepair:
    def _check(self, passed, checks=("cmd",), summary=""):
        v_mod = _v_mod()
        return v_mod.CheckResult(
            passed=passed, checks_run=list(checks), failure_summary=summary
        )

    def test_green_first_try(self, tmp_path):
        v = _v_mod().Verifier(str(tmp_path))
        _script_checks(v, [self._check(True)])
        events = _collect(v.verify_and_repair(
            task="t", change_set=ChangeSet(), context={}, model_router=None
        ))
        types = [e["type"] for e in events]
        assert types == [
            "verification_started", "verification_passed", "verification_summary"
        ]
        assert v.last_report.final_status == "passed"
        assert v.last_report.repair_attempted is False

    def test_no_checks_reports_skipped(self, tmp_path):
        v = _v_mod().Verifier(str(tmp_path))
        _script_checks(v, [self._check(True, checks=())])
        events = _collect(v.verify_and_repair(
            task="t", change_set=ChangeSet(), context={}, model_router=None
        ))
        assert v.last_report.final_status == "skipped"
        assert v.last_report.passed is True
        assert events[-1]["final_status"] == "skipped"

    def test_failure_without_router_exhausts_immediately(self, tmp_path):
        v = _v_mod().Verifier(str(tmp_path))
        _script_checks(v, [self._check(False, summary="boom")])
        events = _collect(v.verify_and_repair(
            task="t", change_set=ChangeSet(), context={}, model_router=None
        ))
        types = [e["type"] for e in events]
        assert "verification_failed" in types
        assert "repair_started" not in types
        exhausted = next(e for e in events if e["type"] == "repair_exhausted")
        assert exhausted["repair_attempts"] == 0
        assert v.last_report.final_status == "failed"
        assert v.last_report.last_failure_summary == "boom"

    def test_repair_succeeds_and_reruns_green(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _RepairAgent)
        main_cs = ChangeSet()
        main_cs.record("mod.py", "x = 1\n", "x = 2\n")

        v = _v_mod().Verifier(str(tmp_path))
        _script_checks(v, [self._check(False, summary="1 failed"), self._check(True)])
        events = _collect(v.verify_and_repair(
            task="t", change_set=main_cs, context={}, model_router=object()
        ))
        types = [e["type"] for e in events]
        assert "repair_started" in types
        assert "repair_succeeded" in types
        assert "verification_passed" in types
        assert "repair_exhausted" not in types
        assert v.last_report.final_status == "passed"
        assert v.last_report.repair_attempts == 1
        # repair edits merged into the main change set
        assert "fix.py" in main_cs.paths

    def test_repair_exhausted_at_default_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _RepairAgent)
        v = _v_mod().Verifier(str(tmp_path), max_repair_attempts=2)
        _script_checks(v, [self._check(False, summary="f")] * 3)
        events = _collect(v.verify_and_repair(
            task="t", change_set=ChangeSet(), context={}, model_router=object()
        ))
        types = [e["type"] for e in events]
        assert types.count("repair_started") == 2
        exhausted = next(e for e in events if e["type"] == "repair_exhausted")
        assert exhausted["repair_attempts"] == 2
        assert v.last_report.final_status == "failed"
        assert v.last_report.repair_attempts == 2

    def test_repair_limit_is_configurable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _RepairAgent)
        v = _v_mod().Verifier(str(tmp_path), max_repair_attempts=1)
        _script_checks(v, [self._check(False, summary="f")] * 2)
        events = _collect(v.verify_and_repair(
            task="t", change_set=ChangeSet(), context={}, model_router=object()
        ))
        types = [e["type"] for e in events]
        assert types.count("repair_started") == 1
        assert v.last_report.repair_attempts == 1

    def test_merge_preserves_pre_run_snapshots(self):
        v_mod = _v_mod()
        main = ChangeSet()
        main.record("new.py", "", "v1\n", existed_before=False)

        repair = ChangeSet()
        repair.record("new.py", "v1\n", "v2\n")
        repair.record("extra.py", "", "e\n", existed_before=False)

        v_mod._merge_change_sets(main, repair)

        edit = {e.path: e for e in main.edits}["new.py"]
        assert edit.existed_before is False     # pre-run state preserved
        assert edit.old_content == ""
        assert edit.new_content == "v2\n"
        extra = {e.path: e for e in main.edits}["extra.py"]
        assert extra.existed_before is False


# ── phased run integration ────────────────────────────────────────────────────

_OLD_MOD = "line1\nline2\n"
_NEW_MOD = "line1\nline2\nline3\n"   # additive edit — passes the gate


class _WriterAgent:
    """AgentLoop stand-in: writes mod.py to disk and records the edit."""
    def __init__(self, model_router=None, repo_path=None, **kwargs):
        self.repo_path = repo_path
        self.last_change_set = ChangeSet()

    async def run_stream(self, **kwargs):
        (Path(self.repo_path) / "mod.py").write_text(_NEW_MOD, encoding="utf-8")
        self.last_change_set.record("mod.py", _OLD_MOD, _NEW_MOD)
        yield {"type": "finish", "success": True, "summary": "done",
               "files": ["mod.py"]}


class _PassingFakeVerifier:
    """Verifier stand-in: fails once, repairs, then passes."""
    def __init__(self, repo_path, checkpoint_cmd=None, max_repair_attempts=2):
        self.last_report = None

    async def verify_and_repair(self, *, task, change_set, context=None,
                                model_router=None, model=None):
        yield {"type": "verification_started"}
        yield {"type": "verification_failed", "checks_run": ["pytest"],
               "failure_summary": "1 failed", "repair_attempts": 0}
        yield {"type": "repair_started", "attempt": 1, "max_repair_attempts": 2}
        yield {"type": "repair_succeeded", "attempt": 1}
        yield {"type": "verification_passed", "checks_run": ["pytest"],
               "repair_attempts": 1}
        self.last_report = _v_mod().VerificationReport(
            final_status="passed", checks_run=["pytest"], passed=True,
            repair_attempted=True, repair_attempts=1,
        )
        yield {"type": "verification_summary", "final_status": "passed",
               "passed": True, "repair_attempts": 1}


class TestPhasedRunVerification:
    def test_failed_verification_halts_and_reverts(self, monkeypatch, tmp_path):
        import app.interactive.phase_runner as pr_mod
        from app.interactive.planner import Phase

        (tmp_path / "mod.py").write_text(_OLD_MOD, encoding="utf-8")
        monkeypatch.setattr(pr_mod, "AgentLoop", _WriterAgent)

        phases = [
            Phase(id="p1", name="one", description="d", specialist="writer",
                  checkpoint_cmd=FAIL_CMD),
            Phase(id="p2", name="two", description="d", specialist="writer",
                  dependencies=["p1"]),
        ]
        runner = pr_mod.PhaseRunner(model_router=None, repo_path=str(tmp_path))
        events = _collect(runner.run_phases(phases=phases, task="t", context={}))

        types = [e["type"] for e in events]
        assert "verification_failed" in types
        assert "repair_exhausted" in types
        assert "run_halted" in types
        assert "phase_checkpoint" not in types          # nothing committed
        started = [e["phase_id"] for e in events if e["type"] == "phase_start"]
        assert started == ["p1"]                        # p2 never started

        halted = next(e for e in events if e["type"] == "run_halted")
        assert halted["reverted"] is True
        assert (tmp_path / "mod.py").read_text() == _OLD_MOD  # reverted on disk
        assert runner.last_verification.final_status == "failed"

    def test_successful_repair_allows_continuation(self, monkeypatch, tmp_path):
        import app.interactive.phase_runner as pr_mod
        from app.interactive.planner import Phase

        (tmp_path / "mod.py").write_text(_OLD_MOD, encoding="utf-8")
        monkeypatch.setattr(pr_mod, "AgentLoop", _WriterAgent)
        monkeypatch.setattr(pr_mod, "Verifier", _PassingFakeVerifier)

        phases = [
            Phase(id="p1", name="one", description="d", specialist="writer"),
            Phase(id="p2", name="two", description="d", specialist="writer",
                  dependencies=["p1"]),
        ]
        runner = pr_mod.PhaseRunner(model_router=None, repo_path=str(tmp_path))
        events = _collect(runner.run_phases(phases=phases, task="t", context={}))

        types = [e["type"] for e in events]
        assert "repair_succeeded" in types
        assert "verification_passed" in types
        assert "run_halted" not in types
        started = [e["phase_id"] for e in events if e["type"] == "phase_start"]
        assert started == ["p1", "p2"]
        assert runner.last_verification.final_status == "passed"


# ── AutoRun (orchestrator) integration ────────────────────────────────────────

class _FailingFakeVerifier:
    """Verifier stand-in: fails and exhausts its repair budget."""
    def __init__(self, repo_path, checkpoint_cmd=None, max_repair_attempts=2):
        self.last_report = None

    async def verify_and_repair(self, *, task, change_set, context=None,
                                model_router=None, model=None):
        yield {"type": "verification_started"}
        yield {"type": "verification_failed", "checks_run": ["pytest"],
               "failure_summary": "1 failed", "repair_attempts": 0}
        yield {"type": "repair_exhausted", "repair_attempts": 2,
               "max_repair_attempts": 2, "failure_summary": "1 failed"}
        self.last_report = _v_mod().VerificationReport(
            final_status="failed", checks_run=["pytest"], passed=False,
            repair_attempted=True, repair_attempts=2,
            last_failure_summary="1 failed",
        )
        yield {"type": "verification_summary", "final_status": "failed",
               "passed": False, "repair_attempts": 2}


class _AutoAgent:
    """AgentLoop stand-in for orchestrator AutoRun tests."""
    next_change_set = None

    def __init__(self, model_router=None, repo_path=None, **kwargs):
        self.repo_path = repo_path
        self.last_change_set = type(self).next_change_set

    async def run(self, task, context, **kwargs):
        return SimpleNamespace(
            success=True, summary="done", tool_calls=[], files_written=[],
            error=None, change_set=type(self).next_change_set,
        )

    async def run_stream(self, task, context, **kwargs):
        yield {"type": "finish", "success": True, "summary": "done", "files": []}


def _make_orchestrator(repo_path):
    from app.interactive.orchestrator import InteractiveOrchestrator

    class _Sessions:
        def create_session(self, ctx=None):
            return "s1"

        def get_session(self, sid):
            return {"id": sid}

        def add_message(self, sid, msg):
            pass

    class _Ctx:
        def gather_context(self, ctx=None):
            return {}

        def build_context_pack(self, task, ctx):
            raise RuntimeError("no pack in tests")

    orch = InteractiveOrchestrator.__new__(InteractiveOrchestrator)
    orch.engine = SimpleNamespace(repo_path=repo_path)
    orch.session_manager = _Sessions()
    orch.model_router = object()
    orch.context_engine = _Ctx()
    orch.action_planner = None
    return orch


class TestAutoRunVerification:
    def _request(self, task="do it"):
        from app.interactive.contracts import AutoRunRequest
        return AutoRunRequest(task=task)

    def test_failed_verification_blocks_success_and_skips_commit(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _AutoAgent)
        monkeypatch.setattr("app.interactive.verifier.Verifier", _FailingFakeVerifier)

        (tmp_path / "mod.py").write_text("broken\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("mod.py", "ok\n", "broken\n")
        _AutoAgent.next_change_set = cs

        orch = _make_orchestrator(str(tmp_path))
        commits = []
        orch._commit_agent_changes = (
            lambda *a, **k: commits.append(a)  # records; returns None
        )

        resp = asyncio.run(orch.handle_auto_run(self._request()))

        assert commits == []                              # commit never attempted
        assert resp.overall_status == "failed"
        assert resp.execution_result.status == "Broken"
        assert resp.execution_result.reverted is True
        assert resp.verification is not None
        assert resp.verification.final_status == "failed"
        assert resp.verification.repair_attempts == 2
        verify_steps = [s for s in resp.steps if s.step_name == "verify"]
        assert verify_steps and verify_steps[0].status == "failed"
        assert (tmp_path / "mod.py").read_text() == "ok\n"  # reverted on disk

    def test_passed_verification_proceeds_to_commit(self, monkeypatch, tmp_path):
        from app.interactive.contracts import ExecutionResultCard

        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _AutoAgent)
        monkeypatch.setattr("app.interactive.verifier.Verifier", _PassingFakeVerifier)

        cs = ChangeSet()
        cs.record("mod.py", "ok\n", "better\n")
        _AutoAgent.next_change_set = cs

        orch = _make_orchestrator(str(tmp_path))
        commits = []

        def fake_commit(session_id, task, change_set, repo_path):
            commits.append(change_set)
            return ExecutionResultCard(
                status="Working", mode="CRITICAL", commit_sha="abc123"
            )

        orch._commit_agent_changes = fake_commit

        resp = asyncio.run(orch.handle_auto_run(self._request()))

        assert len(commits) == 1
        assert resp.overall_status == "success"
        assert resp.verification.final_status == "passed"
        assert resp.verification.repair_attempts == 1
        verify_steps = [s for s in resp.steps if s.step_name == "verify"]
        assert verify_steps and verify_steps[0].status == "success"

    def test_stream_failed_verification_halts_without_commit(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("app.interactive.agent_loop.AgentLoop", _AutoAgent)
        monkeypatch.setattr("app.interactive.verifier.Verifier", _FailingFakeVerifier)

        (tmp_path / "mod.py").write_text("broken\n", encoding="utf-8")
        cs = ChangeSet()
        cs.record("mod.py", "ok\n", "broken\n")
        _AutoAgent.next_change_set = cs

        orch = _make_orchestrator(str(tmp_path))
        orch._commit_agent_changes = (
            lambda *a, **k: pytest.fail("commit must not happen")
        )

        events = _collect(orch.stream_auto_run(self._request()))
        types = [e["type"] for e in events]
        assert "verification_failed" in types
        assert "repair_exhausted" in types
        assert "run_halted" in types
        assert "commit" not in types
        halted = next(e for e in events if e["type"] == "run_halted")
        assert halted["reverted"] is True
        assert (tmp_path / "mod.py").read_text() == "ok\n"


# ── Per-run rollback to pre-run ref ────────────────────────────────────────────

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _init_repo(path):
    _git(["init"], path)
    _git(["config", "user.email", "t@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    _git(["config", "commit.gpgsign", "false"], path)


def _head(path, short=False):
    cmd = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
    return subprocess.run(["git", *cmd], cwd=path, check=True,
                          capture_output=True, text=True).stdout.strip()


class _RollbackSessions:
    """SessionManager stand-in returning a fixed last execution card."""
    def __init__(self, card):
        self._card = card
        self.set_calls = []

    def get_last_execution(self, sid):
        return self._card

    def set_last_execution(self, sid, card):
        self.set_calls.append(card)


def _rollback_orch(repo_path, card):
    from app.interactive.orchestrator import InteractiveOrchestrator
    orch = InteractiveOrchestrator.__new__(InteractiveOrchestrator)
    orch.engine = SimpleNamespace(repo_path=repo_path)
    orch.session_manager = _RollbackSessions(card)
    return orch


def _committed_run(tmp_path):
    """Init a repo, commit 'original', then a run commit 'broken'."""
    repo = str(tmp_path)
    _init_repo(repo)
    (tmp_path / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["commit", "-m", "init"], repo)
    pre = _head(repo)
    (tmp_path / "a.txt").write_text("broken\n", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["commit", "-m", "run"], repo)
    return repo, pre, _head(repo, short=True)


class TestPerRunRollback:
    def test_restores_run_to_pre_run_ref(self, tmp_path):
        from app.interactive.contracts import ExecutionResultCard, RollbackRequest
        repo, pre, sha = _committed_run(tmp_path)
        card = ExecutionResultCard(
            status="Working", mode="CRITICAL", commit_sha=sha, pre_run_ref=pre
        )
        orch = _rollback_orch(repo, card)

        resp = asyncio.run(orch.handle_rollback(RollbackRequest(session_id="s1")))

        assert resp.success is True
        assert resp.restored_to == pre
        assert resp.commit_reverted == sha
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "original\n"
        # last execution cleared so a second rollback is blocked
        assert orch.session_manager.set_calls[-1].commit_sha is None

    def test_fallback_reverts_single_commit_without_pre_run_ref(self, tmp_path):
        from app.interactive.contracts import ExecutionResultCard, RollbackRequest
        repo, _pre, sha = _committed_run(tmp_path)
        card = ExecutionResultCard(
            status="Working", mode="CRITICAL", commit_sha=sha, pre_run_ref=None
        )
        orch = _rollback_orch(repo, card)

        resp = asyncio.run(orch.handle_rollback(RollbackRequest(session_id="s1")))

        assert resp.success is True
        assert resp.restored_to is None
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "original\n"

    def test_no_commit_sha_fails(self, tmp_path):
        from app.interactive.contracts import ExecutionResultCard, RollbackRequest
        card = ExecutionResultCard(status="Working", mode="CRITICAL", commit_sha=None)
        orch = _rollback_orch(str(tmp_path), card)

        resp = asyncio.run(orch.handle_rollback(RollbackRequest(session_id="s1")))

        assert resp.success is False
        assert "commit SHA" in resp.message



