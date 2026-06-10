"""
AGENT NEO - Interactive ChangeSet
Staged file edits recorded by the tool layer during an agent run.
Materialized as a unified diff and gated through the same core pipeline
the Engine applies to diffs (validation -> governance -> push safety)
before anything is committed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

from app.modules.diff_generator import generate_unified_diff, generate_file_deletion_diff
from app.modules.governance import GovernanceValidator, ViolationSeverity
from app.core.validation import validate_diff, parse_diff_metadata
from app.core.policy import validate_push_safety
from app.core.engine import DEFAULT_GOVERNANCE_PROFILE


@dataclass
class StagedEdit:
    """A single staged file change: original content vs. agent-produced state."""
    path: str
    old_content: str
    new_content: str
    operation: str = "edit"  # "edit" (write/create) or "delete"
    existed_before: bool = True
    renamed_from: Optional[str] = None


class ChangeSet:
    """Accumulates file changes made by the agent during a run.

    For repeated changes to the same path, the first old_content (pre-run
    state) and the latest new state win, so the diff reflects the net
    change of the run.
    """

    def __init__(self):
        self._edits: Dict[str, StagedEdit] = {}

    def record(
        self,
        path: str,
        old_content: str,
        new_content: str,
        existed_before: bool = True,
        renamed_from: Optional[str] = None,
    ) -> None:
        existing = self._edits.get(path)
        if existing:
            existing.new_content = new_content
            existing.operation = "edit"
        else:
            self._edits[path] = StagedEdit(
                path=path,
                old_content=old_content,
                new_content=new_content,
                existed_before=existed_before,
                renamed_from=renamed_from,
            )

    def record_delete(self, path: str, old_content: str) -> None:
        existing = self._edits.get(path)
        if existing:
            # Keep the pre-run snapshot; the net result of this run is a delete.
            existing.new_content = ""
            existing.operation = "delete"
        else:
            self._edits[path] = StagedEdit(
                path=path,
                old_content=old_content,
                new_content="",
                operation="delete",
            )

    def record_rename(self, old_path: str, new_path: str, content: str) -> None:
        """A rename is a delete of the old path plus a create of the new path."""
        self.record_delete(old_path, content)
        self.record(new_path, "", content, existed_before=False, renamed_from=old_path)

    @property
    def paths(self) -> List[str]:
        return list(self._edits.keys())

    @property
    def edits(self) -> List[StagedEdit]:
        return list(self._edits.values())

    def is_empty(self) -> bool:
        for e in self._edits.values():
            if e.operation == "delete":
                if e.existed_before:
                    return False
                continue  # created then deleted in this run: net no-op
            if e.old_content != e.new_content:
                return False
        return True

    def to_unified_diff(self) -> str:
        diffs = []
        for e in self._edits.values():
            if e.operation == "delete":
                if e.existed_before:
                    diffs.append(generate_file_deletion_diff(e.path, e.old_content))
                # created-then-deleted in this run: no net change, no diff
            else:
                diff = generate_unified_diff(e.path, e.old_content, e.new_content)
                if diff:
                    diffs.append(diff)
        return ''.join(diffs)

    def revert(self, repo_path: str) -> List[str]:
        """Restore every ChangeSet path to its pre-run state on disk.

        Targeted: only paths recorded in this ChangeSet are touched.
        Returns the list of paths that were reverted.
        """
        reverted = []
        for e in self._edits.values():
            full = Path(repo_path) / e.path
            if e.existed_before:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(e.old_content, encoding="utf-8")
            elif full.exists():
                full.unlink()
            reverted.append(e.path)
        return reverted


@dataclass
class GateResult:
    """Outcome of gating a ChangeSet through the core safety pipeline."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    lines_changed: int = 0
    diff: str = ""


def evaluate_change_set(
    change_set: ChangeSet,
    description: str = "",
    mode: Literal["RAPID", "CRITICAL"] = "CRITICAL",
) -> GateResult:
    """
    Gate a ChangeSet through the same checks Engine.execute() applies to diffs:
    validate_diff -> GovernanceValidator.validate_diff -> validate_push_safety.

    Returns a GateResult; passed=False means the change set must not be committed.
    """
    diff = change_set.to_unified_diff()
    if not diff:
        return GateResult(passed=True)

    errors: List[str] = []
    warnings: List[str] = []

    validation = validate_diff(diff, mode)
    if not validation.valid:
        errors.extend(validation.errors)
    warnings.extend(validation.warnings)

    metadata = parse_diff_metadata(diff)
    governance = GovernanceValidator.validate_diff(
        diff_content=diff,
        description=description,
        files_in_diff=metadata.file_paths,
        profile=DEFAULT_GOVERNANCE_PROFILE,
    )
    warnings.extend(governance.warnings)
    if governance.has_severe:
        errors.extend(
            f"Governance violation [{v.rule_id}]: {v.message}"
            for v in governance.violations
            if v.severity == ViolationSeverity.SEVERE
        )

    safe, reason = validate_push_safety(
        mode=mode,
        files_changed=metadata.files_changed,
        lines_changed=metadata.total_lines_changed,
    )
    if not safe:
        errors.append(reason)

    return GateResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        files=metadata.file_paths,
        lines_changed=metadata.total_lines_changed,
        diff=diff,
    )
