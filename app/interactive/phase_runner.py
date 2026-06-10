"""
AGENT NEO - Phase Runner
Executes a multi-phase plan produced by the Planner.
Each phase runs in a scoped AgentLoop (specialist prompt + tool subset).
A git checkpoint is created after every phase so failures are cheap to roll back.
"""
import logging
import subprocess
from typing import AsyncGenerator, Optional

from app.interactive.planner import Phase
from app.interactive.specialists import get_specialist
from app.interactive.agent_loop import AgentLoop
from app.interactive.change_set import evaluate_change_set
from app.interactive.verifier import Verifier, VerificationReport

logger = logging.getLogger(__name__)


class PhaseRunner:
    def __init__(self, model_router, repo_path: str):
        self.model_router = model_router
        self.repo_path = repo_path
        self.last_verification: Optional[VerificationReport] = None

    async def run_phases(
        self, phases: list[Phase], task: str, context: dict
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator — yields SSE-compatible dicts as each phase runs.

        Event types emitted:
          phase_plan        — upfront list of all phases
          phase_start       — beginning of a phase
          text / tool_start / tool_end — forwarded from AgentLoop.run_stream()
          finish            — forwarded finish event from the specialist
          verification_started / verification_passed / verification_failed
          repair_started / repair_succeeded / repair_exhausted
          verification_summary — final verification outcome for the phase
          change_set_blocked — phase change set rejected by validation/governance
          phase_checkpoint  — git commit SHA after each phase
          phase_end         — summary after a phase completes
          run_halted        — run stopped (phase error, blocked change set,
                              or failed verification)
          error             — if something fatal happens
        """
        yield {
            "type": "phase_plan",
            "phases": [
                {"id": p.id, "name": p.name, "specialist": p.specialist}
                for p in phases
            ],
        }

        ordered = self._topo_sort(phases)
        completed: dict[str, str] = {}  # phase_id → summary text

        for idx, phase in enumerate(ordered):
            specialist = get_specialist(phase.specialist)

            # Build a task message that injects context from prior phases
            prior_ctx = "\n\n".join(
                f"[{pid}]: {completed[pid]}"
                for pid in phase.dependencies
                if pid in completed
            )
            phase_task = phase.description
            if prior_ctx:
                phase_task = (
                    f"{phase_task}\n\nContext from previous phases:\n{prior_ctx}"
                )

            yield {
                "type": "phase_start",
                "phase_id": phase.id,
                "phase_name": phase.name,
                "specialist": phase.specialist,
                "phase_index": idx,
                "total_phases": len(ordered),
            }

            agent = AgentLoop(
                model_router=self.model_router, repo_path=self.repo_path
            )
            phase_summary = f"Phase {phase.id} complete."

            try:
                async for event in agent.run_stream(
                    task=phase_task,
                    context=context,
                    system_override=specialist["system"],
                    tool_subset=specialist["tools"],
                    max_iterations_override=specialist["max_iterations"],
                ):
                    if event.get("type") == "finish":
                        phase_summary = event.get("summary", phase_summary)
                    # Tag every event with its phase for the UI
                    yield {**event, "phase_id": phase.id, "phase_name": phase.name}
            except Exception as exc:
                logger.error(f"Phase {phase.id} failed: {exc}", exc_info=True)
                yield {
                    "type": "error",
                    "phase_id": phase.id,
                    "error": str(exc),
                }
                yield {
                    "type": "run_halted",
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "reason": f"Phase '{phase.name}' raised: {exc}",
                }
                return

            completed[phase.id] = phase_summary

            # ── system-controlled verification + bounded repair ──────────────
            # Editing phases are always verified (regardless of whether the
            # planner supplied a checkpoint_cmd); read-only phases with no
            # edits are verified only if a checkpoint_cmd was given.
            change_set = agent.last_change_set
            if (change_set and not change_set.is_empty()) or phase.checkpoint_cmd:
                verifier = Verifier(
                    self.repo_path, checkpoint_cmd=phase.checkpoint_cmd
                )
                async for v_event in verifier.verify_and_repair(
                    task=phase_task,
                    change_set=change_set,
                    context=context,
                    model_router=self.model_router,
                ):
                    yield {**v_event, "phase_id": phase.id, "phase_name": phase.name}

                report = verifier.last_report
                self.last_verification = report
                if report and not report.passed:
                    reverted = False
                    if change_set and not change_set.is_empty():
                        try:
                            change_set.revert(self.repo_path)
                            reverted = True
                        except Exception as exc:
                            logger.error(
                                f"Failed to revert ChangeSet after failed "
                                f"verification for phase {phase.id}: {exc}",
                                exc_info=True,
                            )
                    yield {
                        "type": "run_halted",
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "reason": (
                            f"Verification failed after "
                            f"{report.repair_attempts} repair attempt(s)"
                        ),
                        "reverted": reverted,
                    }
                    return

            # ── gated git checkpoint (only this phase's change set) ──────────
            if change_set and not change_set.is_empty():
                gate = evaluate_change_set(
                    change_set, description=phase_task, mode="CRITICAL"
                )
                if not gate.passed:
                    reverted = False
                    try:
                        change_set.revert(self.repo_path)
                        reverted = True
                    except Exception as exc:
                        logger.error(
                            f"Failed to revert blocked ChangeSet for phase {phase.id}: {exc}",
                            exc_info=True,
                        )
                    yield {
                        "type": "change_set_blocked",
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "files": change_set.paths,
                        "errors": gate.errors,
                        "reverted": reverted,
                    }
                    yield {
                        "type": "run_halted",
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "reason": "Change set blocked by validation/governance",
                    }
                    return

                sha = self._git_checkpoint(phase.name, change_set.paths)
                if sha:
                    yield {
                        "type": "phase_checkpoint",
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "commit_sha": sha,
                        "files": change_set.paths,
                    }

            yield {
                "type": "phase_end",
                "phase_id": phase.id,
                "phase_name": phase.name,
                "summary": phase_summary,
            }

    # ── helpers ───────────────────────────────────────────────────────────────

    def _topo_sort(self, phases: list[Phase]) -> list[Phase]:
        """Kahn's algorithm — returns phases in valid execution order."""
        in_degree: dict[str, int] = {p.id: 0 for p in phases}
        for p in phases:
            for dep in p.dependencies:
                if dep in in_degree:
                    in_degree[p.id] += 1

        queue = [p for p in phases if in_degree[p.id] == 0]
        ordered: list[Phase] = []
        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for p in phases:
                if current.id in p.dependencies:
                    in_degree[p.id] -= 1
                    if in_degree[p.id] == 0:
                        queue.append(p)

        # Append anything left (e.g. circular deps — shouldn't happen but safe)
        seen = {p.id for p in ordered}
        ordered.extend(p for p in phases if p.id not in seen)
        return ordered

    def _git_checkpoint(self, phase_name: str, paths: list[str]) -> Optional[str]:
        """Stage only the phase's change-set paths + commit.
        Returns short SHA or None if nothing to commit."""
        if not paths:
            return None
        try:
            subprocess.run(
                ["git", "add", "--", *paths],
                cwd=self.repo_path, check=True, capture_output=True, timeout=15,
            )
            proc = subprocess.run(
                ["git", "commit", "-m", f"checkpoint: {phase_name[:60]}"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                sha = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=self.repo_path, capture_output=True, text=True,
                ).stdout.strip()
                logger.info(f"Phase checkpoint: {sha} — {phase_name}")
                return sha
        except Exception as exc:
            logger.warning(f"Phase checkpoint skipped ({phase_name}): {exc}")
        return None

