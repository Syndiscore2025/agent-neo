"""
Tests for the interactive ChangeSet gate (Phase A).

Proves:
1. Interactive commits never use `git add -A` — only staged paths.
2. Only files in the ChangeSet are staged.
3. Governance/validation blocks invalid interactive changes.
4. Failed phase verification halts a phased run.
"""

import pytest

from app.interactive.change_set import ChangeSet, evaluate_change_set
from app.interactive.tools import ToolExecutor
from app.core.validation import parse_diff_metadata


# ── ChangeSet basics ──────────────────────────────────────────────────────────

def test_change_set_records_edits_and_produces_valid_diff():
    cs = ChangeSet()
    cs.record("a.txt", "old\n", "new\n")

    diff = cs.to_unified_diff()
    meta = parse_diff_metadata(diff)

    assert meta.is_valid_unified_diff
    assert meta.file_paths == ["a.txt"]
    assert not cs.is_empty()


def test_change_set_repeated_writes_keep_first_old_latest_new():
    cs = ChangeSet()
    cs.record("a.txt", "v0\n", "v1\n")
    cs.record("a.txt", "v1\n", "v2\n")

    edit = cs.edits[0]
    assert edit.old_content == "v0\n"
    assert edit.new_content == "v2\n"
    assert cs.paths == ["a.txt"]


def test_change_set_noop_write_is_empty():
    cs = ChangeSet()
    cs.record("a.txt", "same\n", "same\n")
    assert cs.is_empty()
    assert cs.to_unified_diff() == ""


def test_tool_executor_write_file_records_change_set(tmp_path):
    (tmp_path / "a.txt").write_text("old\n", encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))

    executor.execute("write_file", {"path": "a.txt", "content": "new\n"})

    assert executor.change_set.paths == ["a.txt"]
    edit = executor.change_set.edits[0]
    assert edit.old_content == "old\n"
    assert edit.new_content == "new\n"


# ── Gate: validation/governance blocks invalid changes ───────────────────────

def test_gate_passes_clean_change():
    cs = ChangeSet()
    cs.record("a.txt", "line 1\nline 2\n", "line 1\nline 2\nline 3\n")

    gate = evaluate_change_set(cs, description="add a line")

    assert gate.passed
    assert gate.errors == []
    assert gate.files == ["a.txt"]


def test_gate_blocks_excessive_deletion():
    # >40% deletion in a file is rejected by validate_diff (CRITICAL mode)
    old = "".join(f"line {i}\n" for i in range(10))
    cs = ChangeSet()
    cs.record("a.txt", old, "line 0\n")

    gate = evaluate_change_set(cs, description="gut the file")

    assert not gate.passed
    assert any("deletion" in e for e in gate.errors)


# ── Gated commit: no `git add -A`, only ChangeSet paths staged ────────────────

class _FakeSessionManager:
    def __init__(self):
        self.cards = []

    def set_last_execution(self, session_id, card):
        self.cards.append((session_id, card))


class _FakeOrch:
    """Minimal stand-in exposing only what _commit_agent_changes uses."""
    def __init__(self):
        self.session_manager = _FakeSessionManager()


def test_gated_commit_stages_only_change_set_paths(monkeypatch, tmp_path):
    import app.interactive.orchestrator as orch_mod

    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))

        class R:
            returncode = 0
            stdout = "abc1234\n"
            stderr = ""
        return R()

    monkeypatch.setattr(orch_mod.subprocess, "run", fake_run)

    cs = ChangeSet()
    cs.record("a.txt", "line 1\nline 2\n", "line 1\nline 2\nline 3\n")

    fake = _FakeOrch()
    card = orch_mod.InteractiveOrchestrator._commit_agent_changes(
        fake, "sess-1", "test task", cs, str(tmp_path)
    )

    add_cmds = [c for c in commands if c[:2] == ["git", "add"]]
    assert add_cmds == [["git", "add", "--", "a.txt"]]
    assert all("-A" not in c for c in commands)
    assert card is not None
    assert card.status == "Working"
    assert card.files_changed == ["a.txt"]
    # pre-run snapshot captured (HEAD read before the commit) for run rollback
    assert card.pre_run_ref == "abc1234"


def test_gated_commit_blocks_invalid_change_without_touching_git(monkeypatch, tmp_path):
    import app.interactive.orchestrator as orch_mod

    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        raise AssertionError("git must not be invoked for a blocked change set")

    monkeypatch.setattr(orch_mod.subprocess, "run", fake_run)

    old = "".join(f"line {i}\n" for i in range(10))
    cs = ChangeSet()
    cs.record("a.txt", old, "line 0\n")

    fake = _FakeOrch()
    card = orch_mod.InteractiveOrchestrator._commit_agent_changes(
        fake, "sess-1", "test task", cs, str(tmp_path)
    )

    assert commands == []
    assert card is not None
    assert card.status == "Broken"
    assert card.commit_sha is None
    assert card.error


# ── Phased run: failures halt execution ───────────────────────────────────────

def _collect(agen):
    import asyncio

    async def go():
        return [e async for e in agen]
    return asyncio.run(go())


class _FakeAgent:
    """AgentLoop stand-in: finishes immediately with an empty change set."""
    def __init__(self, model_router=None, repo_path=None, **kwargs):
        self.last_change_set = ChangeSet()

    async def run_stream(self, **kwargs):
        yield {"type": "finish", "success": True, "summary": "done", "files": []}


def test_failed_phase_verification_halts_run(monkeypatch, tmp_path):
    import app.interactive.phase_runner as pr_mod
    from app.interactive.planner import Phase

    monkeypatch.setattr(pr_mod, "AgentLoop", _FakeAgent)

    phases = [
        Phase(id="p1", name="one", description="d", specialist="writer",
              checkpoint_cmd='python -c "import sys; sys.exit(1)"'),
        Phase(id="p2", name="two", description="d", specialist="writer",
              dependencies=["p1"]),
    ]
    runner = pr_mod.PhaseRunner(model_router=None, repo_path=str(tmp_path))
    events = _collect(runner.run_phases(phases=phases, task="t", context={}))

    types = [e["type"] for e in events]
    assert "run_halted" in types
    started = [e["phase_id"] for e in events if e["type"] == "phase_start"]
    assert started == ["p1"]


def test_blocked_change_set_halts_phased_run(monkeypatch, tmp_path):
    import app.interactive.phase_runner as pr_mod
    from app.interactive.planner import Phase

    class _BadAgent(_FakeAgent):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            old = "".join(f"line {i}\n" for i in range(10))
            self.last_change_set.record("a.txt", old, "line 0\n")

    monkeypatch.setattr(pr_mod, "AgentLoop", _BadAgent)

    phases = [
        Phase(id="p1", name="one", description="d", specialist="writer"),
        Phase(id="p2", name="two", description="d", specialist="writer",
              dependencies=["p1"]),
    ]
    runner = pr_mod.PhaseRunner(model_router=None, repo_path=str(tmp_path))
    events = _collect(runner.run_phases(phases=phases, task="t", context={}))

    types = [e["type"] for e in events]
    assert "change_set_blocked" in types
    assert "run_halted" in types
    assert "phase_checkpoint" not in types
    started = [e["phase_id"] for e in events if e["type"] == "phase_start"]
    assert started == ["p1"]

    blocked = next(e for e in events if e["type"] == "change_set_blocked")
    assert blocked["files"] == ["a.txt"]
    assert blocked["errors"]
    assert blocked["reverted"] is True


# ── Phase A.5: deletions and renames are recorded and gated ──────────────────

def test_tool_executor_delete_file_records_deletion(tmp_path):
    (tmp_path / "a.txt").write_text("line 1\nline 2\n", encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))

    result = executor.execute("delete_file", {"path": "a.txt"})

    assert result.startswith("[ok]")
    assert not (tmp_path / "a.txt").exists()
    edit = executor.change_set.edits[0]
    assert edit.operation == "delete"
    assert edit.old_content == "line 1\nline 2\n"

    diff = executor.change_set.to_unified_diff()
    meta = parse_diff_metadata(diff)
    assert "+++ /dev/null" in diff
    assert meta.is_valid_unified_diff
    assert meta.file_paths == ["a.txt"]
    assert meta.deleted_files == ["a.txt"]


def test_tool_executor_rename_file_records_rename(tmp_path):
    (tmp_path / "a.txt").write_text("content\n", encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))

    result = executor.execute("rename_file", {"old_path": "a.txt", "new_path": "b.txt"})

    assert result.startswith("[ok]")
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "content\n"
    assert set(executor.change_set.paths) == {"a.txt", "b.txt"}

    meta = parse_diff_metadata(executor.change_set.to_unified_diff())
    assert "a.txt" in meta.deleted_files
    assert "b.txt" in meta.file_paths


def test_create_then_delete_nets_to_no_change(tmp_path):
    executor = ToolExecutor(str(tmp_path))
    executor.execute("write_file", {"path": "tmp.txt", "content": "x\n"})
    executor.execute("delete_file", {"path": "tmp.txt"})

    assert executor.change_set.is_empty()
    assert executor.change_set.to_unified_diff() == ""


def test_gate_allows_benign_whole_file_delete():
    cs = ChangeSet()
    cs.record_delete("notes.txt", "line 1\nline 2\nline 3\n")

    gate = evaluate_change_set(cs, description="remove notes")

    assert gate.passed
    assert gate.files == ["notes.txt"]


def test_gate_blocks_dangerous_delete_in_rapid_mode():
    cs = ChangeSet()
    cs.record_delete("Dockerfile", "FROM python:3.11\n")

    gate = evaluate_change_set(cs, description="remove dockerfile", mode="RAPID")

    assert not gate.passed
    assert "Dockerfile" in gate.files
    assert any("Dockerfile" in e for e in gate.errors)


def test_no_commit_when_delete_is_blocked(monkeypatch, tmp_path):
    import app.interactive.orchestrator as orch_mod

    def fake_run(cmd, **kwargs):
        raise AssertionError("git must not be invoked for a blocked change set")

    monkeypatch.setattr(orch_mod.subprocess, "run", fake_run)

    # Deleting a file whose content matches a forbidden pattern is blocked
    content = "deploy:\n    git push --force origin main\n"
    (tmp_path / "deploy.sh").write_text(content, encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))
    executor.execute("delete_file", {"path": "deploy.sh"})

    fake = _FakeOrch()
    card = orch_mod.InteractiveOrchestrator._commit_agent_changes(
        fake, "sess-1", "remove deploy script", executor.change_set, str(tmp_path)
    )

    assert card.status == "Broken"
    assert card.commit_sha is None
    # revert-on-block restored the deleted file
    assert card.reverted
    assert (tmp_path / "deploy.sh").read_text(encoding="utf-8") == content


# ── Phase A.5: revert-on-block ────────────────────────────────────────────────

def test_revert_restores_edited_and_created_files(tmp_path):
    (tmp_path / "edited.txt").write_text("original\n", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("untouched\n", encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))
    executor.execute("write_file", {"path": "edited.txt", "content": "modified\n"})
    executor.execute("write_file", {"path": "created.txt", "content": "new\n"})

    reverted = executor.change_set.revert(str(tmp_path))

    assert set(reverted) == {"edited.txt", "created.txt"}
    assert (tmp_path / "edited.txt").read_text(encoding="utf-8") == "original\n"
    assert not (tmp_path / "created.txt").exists()
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "untouched\n"


def test_revert_restores_deleted_and_renamed_files(tmp_path):
    (tmp_path / "doomed.txt").write_text("keep me\n", encoding="utf-8")
    (tmp_path / "old.txt").write_text("moving\n", encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))
    executor.execute("delete_file", {"path": "doomed.txt"})
    executor.execute("rename_file", {"old_path": "old.txt", "new_path": "new.txt"})

    executor.change_set.revert(str(tmp_path))

    assert (tmp_path / "doomed.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (tmp_path / "old.txt").read_text(encoding="utf-8") == "moving\n"
    assert not (tmp_path / "new.txt").exists()


def test_blocked_commit_reverts_change_set_files(monkeypatch, tmp_path):
    import app.interactive.orchestrator as orch_mod

    def fake_run(cmd, **kwargs):
        raise AssertionError("git must not be invoked for a blocked change set")

    monkeypatch.setattr(orch_mod.subprocess, "run", fake_run)

    old = "".join(f"line {i}\n" for i in range(10))
    (tmp_path / "a.txt").write_text(old, encoding="utf-8")
    executor = ToolExecutor(str(tmp_path))
    # >40% deletion of a small file — blocked by the gate
    executor.execute("write_file", {"path": "a.txt", "content": "line 0\n"})

    fake = _FakeOrch()
    card = orch_mod.InteractiveOrchestrator._commit_agent_changes(
        fake, "sess-1", "gut the file", executor.change_set, str(tmp_path)
    )

    assert card.status == "Broken"
    assert card.reverted
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == old


# ── Phase A.5: human-readable blocked messaging ───────────────────────────────

def test_blocked_message_is_human_readable_for_small_file():
    old = "".join(f"line {i}\n" for i in range(10))
    cs = ChangeSet()
    cs.record("a.txt", old, "line 0\n")

    gate = evaluate_change_set(cs, description="gut the file")

    assert not gate.passed
    assert gate.files == ["a.txt"]
    msg = "; ".join(gate.errors)
    assert "MAX_FILE_DELETION_PERCENT" in msg
    assert "a.txt" in msg
    assert "40% threshold" in msg
