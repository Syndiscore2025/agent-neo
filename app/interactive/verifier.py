"""
AGENT NEO - Verifier
System-controlled verification and bounded repair loop (Phase C).

Runs checks after writer phases / agent runs and before any commit:
  1. phase checkpoint_cmd if provided (command is an input; pass/fail is
     decided by the system from the exit code, never by the model)
  2. targeted pytest run derived from the ChangeSet's changed .py files
  3. fallback to the repo's auto-detected test command

On failure, attempts bounded automated repair via the tester specialist,
merging repair edits back into the run's ChangeSet so the existing
gate/revert pipeline sees the full picture.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from app.interactive.change_set import ChangeSet
from app.modules.tests_runner import run_tests

logger = logging.getLogger(__name__)

# Single configurable place for the repair budget.
MAX_REPAIR_ATTEMPTS = int(os.getenv("NEO_MAX_REPAIR_ATTEMPTS", "2"))

_FAILURE_SUMMARY_LIMIT = 1500
_NO_CHECKS_MESSAGE = "No test command configured"


@dataclass
class CheckResult:
    """Outcome of one verification pass."""
    passed: bool
    checks_run: List[str] = field(default_factory=list)
    failure_summary: str = ""


@dataclass
class VerificationReport:
    """Final verification outcome attached to run results."""
    final_status: str = "skipped"        # "passed" | "failed" | "skipped"
    checks_run: List[str] = field(default_factory=list)
    passed: bool = True
    repair_attempted: bool = False
    repair_attempts: int = 0
    last_failure_summary: str = ""


def _summarize_failure(output: str) -> str:
    """Keep the signal lines (FAILED/ERROR/assert) plus the tail, capped."""
    lines = output.splitlines()
    signal = [
        ln for ln in lines
        if "FAILED" in ln or "ERROR" in ln or "assert" in ln or ln.startswith("E ")
    ]
    tail = lines[-15:]
    seen: set = set()
    combined: List[str] = []
    for ln in signal + tail:
        if ln not in seen:
            seen.add(ln)
            combined.append(ln)
    summary = "\n".join(combined).strip() or output.strip()
    return summary[-_FAILURE_SUMMARY_LIMIT:]


def _targeted_test_paths(repo_path: str, change_set: Optional[ChangeSet]) -> List[str]:
    """Derive test files to run from the changed .py paths."""
    if not change_set:
        return []
    root = Path(repo_path)
    targets: List[str] = []
    for rel in change_set.paths:
        if not rel.endswith(".py"):
            continue
        p = Path(rel)
        name = p.name
        if name.startswith("test_") or name.endswith("_test.py"):
            if (root / rel).is_file():
                targets.append(rel)
            continue
        stem = p.stem
        for candidate in (
            Path("tests") / f"test_{stem}.py",
            p.parent / f"test_{stem}.py",
        ):
            if (root / candidate).is_file():
                targets.append(str(candidate).replace(os.sep, "/"))
    # de-dupe, preserve order
    seen: set = set()
    unique = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


class Verifier:
    """System-controlled verification + bounded repair for one run/phase."""

    def __init__(
        self,
        repo_path: str,
        checkpoint_cmd: Optional[str] = None,
        max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    ):
        self.repo_path = repo_path
        self.checkpoint_cmd = checkpoint_cmd
        self.max_repair_attempts = max_repair_attempts
        self.last_report: Optional[VerificationReport] = None

    # ── check selection + execution ───────────────────────────────────────

    def run_checks(self, change_set: Optional[ChangeSet] = None) -> CheckResult:
        """Run the most targeted checks available; system decides pass/fail."""
        if self.checkpoint_cmd:
            command = self.checkpoint_cmd
        else:
            targets = _targeted_test_paths(self.repo_path, change_set)
            if targets:
                command = "python -m pytest " + " ".join(targets) + " --tb=short -q"
            else:
                command = None  # fall back to repo auto-detection

        result = run_tests(self.repo_path, test_command=command)
        if command is None and _NO_CHECKS_MESSAGE in result.output:
            # Nothing detectable to run — safe default, recorded as no checks.
            return CheckResult(passed=True, checks_run=[], failure_summary="")

        ran = command or "(auto-detected test command)"
        if result.passed:
            return CheckResult(passed=True, checks_run=[ran])
        return CheckResult(
            passed=False,
            checks_run=[ran],
            failure_summary=_summarize_failure(result.output),
        )

    # ── bounded repair loop ───────────────────────────────────────────────

    async def verify_and_repair(
        self,
        *,
        task: str,
        change_set: Optional[ChangeSet],
        context: Optional[dict] = None,
        model_router=None,
    ) -> AsyncGenerator[dict, None]:
        """
        Run checks; on failure attempt bounded repair via the tester
        specialist, merging repair edits into `change_set`, then re-verify.

        Yields structured events and ends with a 'verification_summary'
        event. The final report is also stored in self.last_report.
        """
        report = VerificationReport()
        self.last_report = report

        yield {"type": "verification_started"}
        check = self.run_checks(change_set)
        report.checks_run = list(check.checks_run)

        attempts = 0
        while not check.passed:
            report.last_failure_summary = check.failure_summary
            yield {
                "type": "verification_failed",
                "checks_run": check.checks_run,
                "failure_summary": check.failure_summary,
                "repair_attempts": attempts,
            }

            if model_router is None or attempts >= self.max_repair_attempts:
                report.final_status = "failed"
                report.passed = False
                report.repair_attempted = attempts > 0
                report.repair_attempts = attempts
                yield {
                    "type": "repair_exhausted",
                    "repair_attempts": attempts,
                    "max_repair_attempts": self.max_repair_attempts,
                    "failure_summary": check.failure_summary,
                }
                yield self._summary_event(report)
                return

            attempts += 1
            report.repair_attempted = True
            report.repair_attempts = attempts
            yield {
                "type": "repair_started",
                "attempt": attempts,
                "max_repair_attempts": self.max_repair_attempts,
            }

            try:
                repair_change_set = await self._run_repair(
                    task=task,
                    failure=check,
                    change_set=change_set,
                    context=context or {},
                    model_router=model_router,
                )
                if change_set is not None and repair_change_set is not None:
                    _merge_change_sets(change_set, repair_change_set)
            except Exception as exc:
                logger.error(f"Repair attempt {attempts} raised: {exc}", exc_info=True)

            check = self.run_checks(change_set)
            for c in check.checks_run:
                if c not in report.checks_run:
                    report.checks_run.append(c)
            if check.passed:
                yield {"type": "repair_succeeded", "attempt": attempts}

        report.final_status = "passed" if report.checks_run else "skipped"
        report.passed = True
        report.last_failure_summary = ""
        yield {
            "type": "verification_passed",
            "checks_run": report.checks_run,
            "repair_attempts": attempts,
        }
        yield self._summary_event(report)

    async def _run_repair(
        self,
        *,
        task: str,
        failure: CheckResult,
        change_set: Optional[ChangeSet],
        context: dict,
        model_router,
    ) -> Optional[ChangeSet]:
        """One repair attempt with the tester specialist; returns its ChangeSet."""
        from app.interactive.agent_loop import AgentLoop
        from app.interactive.specialists import get_specialist

        specialist = get_specialist("tester")
        changed = ", ".join(change_set.paths) if change_set else "(none recorded)"
        checks = "; ".join(failure.checks_run) or "(none)"
        repair_task = (
            f"Verification failed after working on this task:\n{task}\n\n"
            f"Files changed so far: {changed}\n"
            f"Failing check(s): {checks}\n\n"
            f"Failure output:\n{failure.failure_summary}\n\n"
            "Fix the cause of the failure with the smallest safe change, "
            "then re-run the failing check with run_command to confirm it passes."
        )

        agent = AgentLoop(model_router=model_router, repo_path=self.repo_path)
        result = await agent.run(
            task=repair_task,
            context=context,
            system_override=specialist["system"],
            tool_subset=specialist["tools"],
            max_iterations_override=specialist["max_iterations"],
        )
        return result.change_set

    def _summary_event(self, report: VerificationReport) -> dict:
        return {
            "type": "verification_summary",
            "final_status": report.final_status,
            "checks_run": report.checks_run,
            "passed": report.passed,
            "repair_attempted": report.repair_attempted,
            "repair_attempts": report.repair_attempts,
            "last_failure_summary": report.last_failure_summary,
        }


def _merge_change_sets(main: ChangeSet, repair: ChangeSet) -> None:
    """
    Fold a repair run's edits into the main ChangeSet using its public API.
    record() keeps the FIRST old_content for a path, so pre-run snapshots
    and existed_before flags (and therefore revert semantics) are preserved.
    """
    for edit in repair.edits:
        if edit.operation == "delete":
            main.record_delete(edit.path, edit.old_content)
        else:
            main.record(
                edit.path,
                edit.old_content,
                edit.new_content,
                existed_before=edit.existed_before,
                renamed_from=edit.renamed_from,
            )

