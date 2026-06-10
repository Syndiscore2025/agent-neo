"""
AGENT NEO - Interactive Orchestrator
Main orchestration logic for interactive chat workflow.
"""

import logging
import os
import subprocess
from typing import Optional
from datetime import datetime

import time
from app.interactive.contracts import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ApprovalRequest,
    ApprovalResponse,
    ActionType,
    ExecutionResultCard,
    SummarizeRequest,
    SessionSummaryResponse,
    RollbackRequest,
    RollbackResponse,
    AutoRunRequest,
    AutoRunResponse,
    AutoRunStep,
    ContextPack,
    VerificationSummary,
)
from app.interactive.session_manager import get_session_manager
from app.interactive.model_router import get_model_router
from app.interactive.context_engine import get_context_engine
from app.interactive.action_planner import get_action_planner
from app.interactive.attachment_handler import get_attachment_handler
from app.core.contracts import TaskRequest
from app.core.engine import Engine

logger = logging.getLogger(__name__)


class InteractiveOrchestrator:
    """
    Orchestrates the interactive chat workflow.
    
    Flow:
    1. Receive user message
    2. Gather context
    3. Route to model
    4. Plan action
    5. Return response (conversational or diff proposal)
    6. If diff proposal, wait for approval
    7. On approval, execute via Agent NEO engine
    """
    
    def __init__(self, engine: Engine):
        """
        Initialize orchestrator.
        
        Args:
            engine: Agent NEO execution engine
        """
        self.engine = engine
        self.session_manager = get_session_manager()
        self.model_router = get_model_router()
        self.context_engine = get_context_engine()
        self.action_planner = get_action_planner()
    
    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """
        Handle chat message.

        Args:
            request: Chat request

        Returns:
            Chat response
        """
        # Get or create session
        session_id = request.session_id
        if not session_id:
            session_id = self.session_manager.create_session(request.context)

        session = self.session_manager.get_session(session_id)
        if not session:
            session_id = self.session_manager.create_session(request.context)
            session = self.session_manager.get_session(session_id)

        # Add user message to session
        user_message = ChatMessage(
            role="user",
            content=request.message
        )
        self.session_manager.add_message(session_id, user_message)

        # Gather context
        context = self.context_engine.gather_context(request.context)

        # Detect intent first
        intent = self.action_planner.detect_intent(request.message)

        # Collect attachment content if any IDs were provided
        attachment_context = ""
        if request.attachment_ids:
            attachment_handler = get_attachment_handler()
            for att_id in request.attachment_ids:
                att = attachment_handler.get_attachment(att_id)
                if att and att.extracted_content:
                    attachment_context += (
                        f"\n[Attachment: {att.file_name}]\n{att.extracted_content}\n"
                    )
            if attachment_context:
                logger.info(
                    f"Injecting {len(request.attachment_ids)} attachment(s) into prompt "
                    f"for session {session_id}"
                )

        # Build enriched prompt with context and intent
        enriched_prompt = self._build_enriched_prompt(
            user_message=request.message,
            context=context,
            session=session,
            intent=intent,
            attachment_context=attachment_context,
        )

        # Generate model response — honour user's model preference if supplied
        # (generate_response resolves any model id, falling back to default)
        selected_model = getattr(request, "model", None)
        logger.info(f"Generating response for session {session_id} (intent: {intent}, model: {selected_model})")
        model_response = await self.model_router.generate_response(
            prompt=enriched_prompt,
            model=selected_model,
            max_tokens=4000
        )

        # Plan action based on response
        action_plan = self.action_planner.plan_action(
            user_message=request.message,
            model_response=model_response,
            context=context
        )

        # Add assistant message to session
        assistant_message = ChatMessage(
            role="assistant",
            content=model_response
        )
        self.session_manager.add_message(session_id, assistant_message)

        # Handle diff proposal if detected
        proposed_diff = None
        if action_plan["action_type"] == ActionType.DIFF_PROPOSAL and action_plan.get("diff"):
            try:
                proposed_diff = self.action_planner.create_diff_proposal(
                    diff=action_plan["diff"],
                    summary=self._extract_summary_from_response(model_response)
                )
                # Store diff in session for later approval
                self.session_manager.set_proposed_diff(session_id, proposed_diff)
                logger.info(f"Diff proposal created for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to create diff proposal: {e}")

        # Build response
        response = ChatResponse(
            session_id=session_id,
            message=model_response,
            action_type=action_plan["action_type"],
            proposed_diff=proposed_diff
        )

        logger.info(f"Chat response generated for session {session_id}")
        return response

    def _extract_summary_from_response(self, response: str) -> str:
        """
        Extract a summary from the model response.

        Args:
            response: Model response

        Returns:
            Summary string
        """
        # Take first paragraph or first 200 characters
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('```'):
                return line[:200]
        return "Code modification"

    def _build_enriched_prompt(
        self,
        user_message: str,
        context: dict,
        session: any,
        intent: str = "conversational",
        attachment_context: str = "",
    ) -> str:
        """
        Build enriched prompt with context and history.

        Args:
            user_message: User's message
            context: Gathered context
            session: Chat session

        Returns:
            Enriched prompt string
        """
        parts = []

        # ── Action-first system prompt ────────────────────────────────────────
        parts.append("You are Agent NEO — an autonomous AI coding agent, not a chatbot.")
        parts.append("")
        parts.append("CRITICAL RULES — follow these without exception:")
        parts.append("1. NEVER say 'Let me know how you'd like to proceed' or any variant.")
        parts.append("2. NEVER acknowledge a request and wait. START WORKING IMMEDIATELY.")
        parts.append("3. NEVER ask clarifying questions unless a required value is truly unknowable.")
        parts.append("4. When given a task, requirement, or description — execute it. Read the relevant")
        parts.append("   files, write the code, apply the changes. Don't narrate. Do.")
        parts.append("5. If you propose a code change, include the FULL unified diff in a ```diff block.")
        parts.append("6. After making changes, briefly summarise what was done (past tense, factual).")
        parts.append("7. Pure questions (no code involved) get a direct, concise answer — no preamble.")
        parts.append("")
        parts.append("Diff format when making changes:")
        parts.append("```diff")
        parts.append("--- a/path/to/file.ext")
        parts.append("+++ b/path/to/file.ext")
        parts.append("@@ -10,3 +10,4 @@")
        parts.append(" unchanged line")
        parts.append("-removed line")
        parts.append("+added line")
        parts.append("```")
        parts.append("")

        # Add repository context
        if context.get("repo_summary"):
            summary = context["repo_summary"]
            parts.append(f"Repository context:")
            parts.append(f"- Total files: {summary.get('total_files', 0)}")
            parts.append(f"- Total lines: {summary.get('total_lines', 0)}")
            parts.append(f"- Languages: {', '.join(summary.get('languages', []))}")
            parts.append(f"- Has tests: {summary.get('has_tests', False)}")
            parts.append("")

        # Add current file context
        if context.get("current_file"):
            parts.append(f"Current file: {context['current_file']}")
            if context.get("language"):
                parts.append(f"Language: {context['language']}")
            parts.append("")

        # Add selected code or full file content
        if context.get("selected_code"):
            parts.append("Selected code:")
            parts.append("```")
            parts.append(context["selected_code"])
            parts.append("```")
            parts.append("")
        elif context.get("current_file_content"):
            parts.append("Current file content:")
            parts.append("```")
            parts.append(context["current_file_content"])
            parts.append("```")
            parts.append("")

        # Add related files
        if context.get("related_files"):
            related = context["related_files"][:3]
            if related:
                parts.append("Related files:")
                for r in related:
                    if isinstance(r, dict):
                        parts.append(f"- {r['path']} ({r.get('reason', 'related')})")
                    else:
                        parts.append(f"- {r}")
                parts.append("")

        # Add attachment context if provided
        if attachment_context.strip():
            parts.append("Attached files:")
            parts.append(attachment_context.strip())
            parts.append("")

        # Add recent conversation history (last 5 messages)
        if session and len(session.messages) > 1:
            parts.append("Recent conversation:")
            recent_messages = session.messages[-6:-1]  # Exclude current message
            for msg in recent_messages:
                parts.append(f"{msg.role}: {msg.content[:200]}...")
            parts.append("")

        # Add user's current message
        parts.append(f"User: {user_message}")

        return "\n".join(parts)
    
    async def handle_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """
        Handle diff approval/rejection.

        Args:
            request: Approval request

        Returns:
            Approval response with execution result
        """
        session = self.session_manager.get_session(request.session_id)
        if not session:
            raise ValueError(f"Session not found: {request.session_id}")

        if not request.approved:
            # User rejected the diff
            self.session_manager.clear_proposed_diff(request.session_id)
            logger.info(f"User rejected diff for session {request.session_id}")
            return ApprovalResponse(
                session_id=request.session_id,
                approved=False,
                message="✗ Changes rejected. How else can I help?"
            )

        # User approved - execute via Agent NEO
        proposed_diff = self.session_manager.get_proposed_diff(request.session_id)
        if not proposed_diff:
            raise ValueError("No proposed diff to execute")

        logger.info(f"Executing approved diff for session {request.session_id}")

        try:
            # Create TaskRequest for Agent NEO engine.
            # Always use CRITICAL mode for interactive changes:
            #   - Commits locally so there is always an audit trail.
            #   - Auto-push is controlled by request.push (force flag).
            #     "Apply Changes" → push=False → commits only.
            #     "Commit & Push" → push=True  → commits AND pushes.
            task_request = TaskRequest(
                task_id=f"chat-{request.session_id}-{int(datetime.utcnow().timestamp())}",
                description="User-approved changes from interactive chat",
                diff=proposed_diff,
                mode="CRITICAL",
                force=request.push
            )

            # Execute via existing Agent NEO pipeline
            execution_result = self.engine.execute(task_request)

            # Clear proposed diff after successful execution
            self.session_manager.clear_proposed_diff(request.session_id)

            # Build typed result card (no invalid fields referenced)
            result_card = ExecutionResultCard(
                status=execution_result.status,
                mode=execution_result.mode,
                commit_sha=execution_result.commit_sha,
                files_changed=execution_result.files_changed,
                lines_changed=execution_result.lines_changed,
                pushed=execution_result.pushed,
                verify_steps=execution_result.verify_steps or [],
                rollback_command=execution_result.rollback_command,
                pre_test_passed=(
                    execution_result.pre_test_result.passed
                    if execution_result.pre_test_result else None
                ),
                post_test_passed=(
                    execution_result.post_test_result.passed
                    if execution_result.post_test_result else None
                ),
                validation_passed=(
                    execution_result.validation_result.passed
                    if execution_result.validation_result else None
                ),
                error=execution_result.error,
            )

            # Persist for rollback
            self.session_manager.set_last_execution(request.session_id, result_card)

            # Format success message
            message = f"✓ Changes applied successfully!\n"
            message += f"Status: {execution_result.status} | Mode: {execution_result.mode}\n"
            if execution_result.commit_sha:
                message += f"Commit: {execution_result.commit_sha[:8]}\n"
            if execution_result.files_changed:
                message += f"Files changed: {len(execution_result.files_changed)}\n"
            if execution_result.pushed:
                message += "Pushed to remote ✓\n"

            logger.info(
                f"Diff executed successfully for session {request.session_id} | "
                f"status={execution_result.status} | mode={execution_result.mode}"
            )

            return ApprovalResponse(
                session_id=request.session_id,
                approved=True,
                message=message,
                execution_result=result_card,
            )

        except Exception as e:
            logger.error(f"Execution failed for session {request.session_id}: {e}", exc_info=True)

            # Clear proposed diff even on failure
            self.session_manager.clear_proposed_diff(request.session_id)

            return ApprovalResponse(
                session_id=request.session_id,
                approved=True,
                message=f"✗ Execution failed: {str(e)}",
                execution_result=ExecutionResultCard(
                    status="Broken",
                    mode="CRITICAL",
                    error=str(e),
                ),
            )


    # ------------------------------------------------------------------
    # Thread-switching: summarise + hand off to a new session
    # ------------------------------------------------------------------
    async def handle_summarize(self, request: SummarizeRequest) -> SessionSummaryResponse:
        """
        Summarise the current session with the LLM and start a fresh session
        whose system context is pre-seeded with that summary.

        This lets the user continue working without hitting context limits.
        """
        session = self.session_manager.get_session(request.session_id)
        if not session:
            raise ValueError(f"Session not found: {request.session_id}")

        message_count = len(session.messages)

        # Build a transcript for the LLM to summarise
        transcript_parts = ["CONVERSATION TRANSCRIPT TO SUMMARISE:"]
        for msg in session.messages[-40:]:   # cap at last 40 to avoid huge prompts
            transcript_parts.append(f"{msg.role.upper()}: {msg.content[:500]}")
        transcript = "\n".join(transcript_parts)

        summarize_prompt = (
            "You are an expert technical assistant. "
            "Produce a concise but complete summary (max 400 words) of the "
            "developer conversation below. Cover: goal, files touched, decisions made, "
            "open questions, and next suggested steps. This summary will be used as "
            "context for a fresh chat session.\n\n"
            + transcript
        )

        try:
            summary_text = await self.model_router.generate_response(
                prompt=summarize_prompt,
                max_tokens=600,
            )
        except Exception as exc:
            logger.warning(f"LLM summarisation failed, using fallback: {exc}")
            summary_text = (
                f"Continuing from previous session ({message_count} messages). "
                "The conversation covered code changes in this repository."
            )

        # Create a new session seeded with the summary as a system message
        new_session_id = self.session_manager.create_session(session.context)
        from app.interactive.contracts import ChatMessage as _CM
        system_seed = _CM(
            role="system",
            content=f"[Continuation context from previous thread]\n{summary_text}",
        )
        self.session_manager.add_message(new_session_id, system_seed)

        logger.info(
            f"Thread handoff: old={request.session_id} ({message_count} msgs) → "
            f"new={new_session_id}"
        )

        return SessionSummaryResponse(
            old_session_id=request.session_id,
            new_session_id=new_session_id,
            summary=summary_text,
            message_count_was=message_count,
        )

    # ------------------------------------------------------------------
    # Rollback: git-revert the last applied commit (local only, no push)
    # ------------------------------------------------------------------
    async def handle_rollback(self, request: RollbackRequest) -> RollbackResponse:
        """
        Revert the last committed change using ``git revert --no-edit``.
        The revert is committed locally; it is never pushed automatically.
        """
        last = self.session_manager.get_last_execution(request.session_id)
        if not last:
            return RollbackResponse(
                session_id=request.session_id,
                success=False,
                message="No previous execution found for this session — nothing to roll back.",
            )

        commit_sha = last.commit_sha
        if not commit_sha:
            return RollbackResponse(
                session_id=request.session_id,
                success=False,
                message="Previous execution did not produce a commit SHA — cannot roll back.",
            )

        repo_path = getattr(self.engine, "repo_path", None)
        try:
            result = subprocess.run(
                ["git", "revert", "--no-edit", commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(
                    f"Rollback succeeded for session {request.session_id}: "
                    f"reverted {commit_sha[:8]}"
                )
                # Clear the stored execution so double-rollback is blocked
                self.session_manager.set_last_execution(
                    request.session_id,
                    ExecutionResultCard(
                        status="Working", mode="CRITICAL",
                        error=None, commit_sha=None
                    ),
                )
                return RollbackResponse(
                    session_id=request.session_id,
                    success=True,
                    message=f"✓ Rolled back commit {commit_sha[:8]} successfully (local revert commit created).",
                    commit_reverted=commit_sha,
                )
            else:
                err = result.stderr.strip() or result.stdout.strip()
                logger.error(f"git revert failed for session {request.session_id}: {err}")
                return RollbackResponse(
                    session_id=request.session_id,
                    success=False,
                    message=f"✗ git revert failed: {err}",
                    commit_reverted=commit_sha,
                )
        except Exception as exc:
            logger.error(f"Rollback exception for session {request.session_id}: {exc}", exc_info=True)
            return RollbackResponse(
                session_id=request.session_id,
                success=False,
                message=f"✗ Rollback error: {str(exc)}",
            )


    # ------------------------------------------------------------------
    # Autonomous task runner — Augment-style agentic ReAct loop
    # ------------------------------------------------------------------
    def _attach_context_pack(
        self, context: dict, task: str, chat_context
    ) -> Optional[ContextPack]:
        """
        Build a task-aware context pack and attach machine-readable summaries
        to the context dict consumed by the planner and agent prompts.
        Never raises — context selection must not break a run.
        """
        try:
            pack = self.context_engine.build_context_pack(task, chat_context)
        except Exception as exc:
            logger.warning(f"Context pack unavailable: {exc}")
            return None
        context["context_summary"] = pack.summary
        context["context_files_with_reasons"] = [
            f.model_dump() for f in pack.primary_files + pack.supporting_files
        ]
        return pack

    async def handle_auto_run(self, request: AutoRunRequest) -> AutoRunResponse:
        """
        Execute a task using a true tool-calling ReAct agent.

        The agent can read/write files, run shell commands, and search the
        codebase.  It loops autonomously until it calls `finish` or hits the
        iteration cap.  Every file it writes is committed to git via CRITICAL
        mode so the change is always reversible.
        """
        from app.interactive.agent_loop import AgentLoop

        # Resolve / create session
        session_id = request.session_id
        if not session_id:
            session_id = self.session_manager.create_session(request.context)
        session = self.session_manager.get_session(session_id)
        if not session:
            session_id = self.session_manager.create_session(request.context)

        context = self.context_engine.gather_context(request.context)
        pack = self._attach_context_pack(context, request.task, request.context)

        repo_path = (
            getattr(request.context, "workspace_path", None)
            or getattr(self.engine, "repo_path", None)
            or os.getenv("REPO_PATH", ".")
        )

        agent = AgentLoop(
            model_router=self.model_router, repo_path=repo_path,
            model=getattr(request, "model", None),
        )

        t_start = time.monotonic()
        try:
            result = await agent.run(task=request.task, context=context)
        except Exception as exc:
            logger.error(f"AgentLoop raised for session {session_id}: {exc}", exc_info=True)
            return AutoRunResponse(
                session_id=session_id, task=request.task,
                steps=[AutoRunStep(step_name="agent", status="failed",
                                   message=str(exc), duration_ms=0)],
                overall_status="failed",
                summary=f"Agent error: {exc}",
            )

        total_ms = int((time.monotonic() - t_start) * 1000)
        steps = self._agent_result_to_steps(result, total_ms)

        # System-controlled verification + bounded repair before any commit
        verification: Optional[VerificationSummary] = None
        if result.change_set and not result.change_set.is_empty():
            from app.interactive.verifier import Verifier

            verifier = Verifier(repo_path)
            t_verify = time.monotonic()
            async for _ in verifier.verify_and_repair(
                task=request.task,
                change_set=result.change_set,
                context=context,
                model_router=self.model_router,
                model=getattr(request, "model", None),
            ):
                pass
            verify_ms = int((time.monotonic() - t_verify) * 1000)
            report = verifier.last_report
            if report:
                verification = self._verification_summary(report)
                steps.append(AutoRunStep(
                    step_name="verify",
                    status="success" if report.passed else "failed",
                    message=(
                        f"Checks: {', '.join(report.checks_run) or 'none detected'}"
                        + ("" if report.passed
                           else f" — {report.last_failure_summary}")
                    ),
                    duration_ms=verify_ms,
                ))

        # Gate + commit the agent's staged change set (never `git add -A`)
        result_card: Optional[ExecutionResultCard] = None
        if verification and not verification.passed:
            reverted = False
            try:
                result.change_set.revert(repo_path)
                reverted = True
            except Exception as exc:
                logger.error(
                    f"Failed to revert ChangeSet after failed verification: {exc}",
                    exc_info=True,
                )
            result_card = ExecutionResultCard(
                status="Broken",
                mode="CRITICAL",
                files_changed=result.change_set.paths,
                error=f"Verification failed: {verification.last_failure_summary}",
                reverted=reverted,
            )
        elif result.change_set and not result.change_set.is_empty():
            result_card = self._commit_agent_changes(
                session_id, request.task, result.change_set, repo_path
            )

        overall = "success" if result.success else "failed"
        if result_card and result_card.status == "Broken":
            overall = "failed"
        summary = result.summary

        self.session_manager.add_message(session_id, ChatMessage(
            role="assistant", content=f"[AutoRun] {summary}"
        ))

        return AutoRunResponse(
            session_id=session_id,
            task=request.task,
            steps=steps,
            overall_status=overall,
            summary=summary,
            execution_result=result_card,
            context_summary=pack.summary if pack else None,
            context_files=(pack.primary_files + pack.supporting_files) if pack else [],
            verification=verification,
        )

    async def stream_auto_run(self, request: AutoRunRequest):
        """
        Async generator — streams SSE-compatible dicts from AgentLoop.run_stream().
        Yields dicts matching StreamEvent schema (type, tool, result, content, etc.)
        """
        from app.interactive.agent_loop import AgentLoop

        session_id = request.session_id
        if not session_id:
            session_id = self.session_manager.create_session(request.context)
        if not self.session_manager.get_session(session_id):
            session_id = self.session_manager.create_session(request.context)

        context = self.context_engine.gather_context(request.context)
        # Inject diagnostics from request context into gathered context
        if request.context and getattr(request.context, "diagnostics", None):
            context["diagnostics"] = request.context.diagnostics

        pack = self._attach_context_pack(context, request.task, request.context)
        if pack:
            yield {
                "type": "context_ready",
                "summary": pack.summary,
                "files": context["context_files_with_reasons"],
            }

        repo_path = (
            getattr(request.context, "workspace_path", None)
            or getattr(self.engine, "repo_path", None)
            or os.getenv("REPO_PATH", ".")
        )
        agent = AgentLoop(
            model_router=self.model_router, repo_path=repo_path,
            model=getattr(request, "model", None),
        )

        try:
            async for event in agent.run_stream(task=request.task, context=context):
                yield event
        except Exception as exc:
            logger.error(f"stream_auto_run error: {exc}", exc_info=True)
            yield {"type": "error", "error": str(exc)}
            return

        # Verification + bounded repair, then gated commit (never `git add -A`)
        change_set = agent.last_change_set
        if change_set and not change_set.is_empty():
            from app.interactive.verifier import Verifier

            verifier = Verifier(repo_path)
            async for v_event in verifier.verify_and_repair(
                task=request.task,
                change_set=change_set,
                context=context,
                model_router=self.model_router,
                model=getattr(request, "model", None),
            ):
                yield v_event

            report = verifier.last_report
            if report and not report.passed:
                reverted = False
                try:
                    change_set.revert(repo_path)
                    reverted = True
                except Exception as exc:
                    logger.error(
                        f"Failed to revert ChangeSet after failed verification: {exc}",
                        exc_info=True,
                    )
                yield {
                    "type": "run_halted",
                    "reason": (
                        f"Verification failed after "
                        f"{report.repair_attempts} repair attempt(s)"
                    ),
                    "reverted": reverted,
                }
            else:
                card = self._commit_agent_changes(session_id, request.task, change_set, repo_path)
                if card and card.status == "Broken":
                    yield {
                        "type": "change_set_blocked",
                        "files": change_set.paths,
                        "errors": card.error,
                        "reverted": card.reverted,
                    }
                elif card and card.commit_sha:
                    yield {
                        "type": "commit",
                        "sha": card.commit_sha,
                        "files": change_set.paths,
                    }
        else:
            yield {"type": "no_changes"}

        self.session_manager.add_message(session_id, ChatMessage(
            role="assistant", content=f"[AutoRun stream] {request.task}"
        ))

    async def stream_phased_run(self, request: AutoRunRequest):
        """
        Async generator — runs a multi-phase agentic plan and streams SSE events.

        Flow:
          1. Emit 'planning' event
          2. Call TaskPlanner → list of Phase objects
          3. Emit 'phase_plan' event
          4. Delegate to PhaseRunner which streams per-phase events
          5. After all phases, emit final 'done' event
        """
        from app.interactive.planner import plan_task
        from app.interactive.phase_runner import PhaseRunner

        session_id = request.session_id
        if not session_id:
            session_id = self.session_manager.create_session(request.context)
        if not self.session_manager.get_session(session_id):
            session_id = self.session_manager.create_session(request.context)

        context = self.context_engine.gather_context(request.context)
        if request.context and getattr(request.context, "diagnostics", None):
            context["diagnostics"] = request.context.diagnostics

        pack = self._attach_context_pack(context, request.task, request.context)
        if pack:
            yield {
                "type": "context_ready",
                "summary": pack.summary,
                "files": context["context_files_with_reasons"],
            }

        repo_path = (
            getattr(request.context, "workspace_path", None)
            or getattr(self.engine, "repo_path", None)
            or os.getenv("REPO_PATH", ".")
        )

        # ── 1. Planning ───────────────────────────────────────────────────────
        yield {"type": "planning", "task": request.task}

        try:
            phases = await plan_task(
                model_router=self.model_router,
                task=request.task,
                context=context,
            )
        except Exception as exc:
            logger.error(f"Planner failed: {exc}", exc_info=True)
            yield {"type": "error", "error": f"Planning failed: {exc}"}
            return

        # ── 2. Execute phases ─────────────────────────────────────────────────
        runner = PhaseRunner(
            model_router=self.model_router, repo_path=repo_path,
            model=getattr(request, "model", None),
        )
        files_written: list[str] = []

        try:
            async for event in runner.run_phases(
                phases=phases, task=request.task, context=context
            ):
                if event.get("type") == "tool_end" and event.get("tool") == "write_file":
                    if event.get("path"):
                        files_written.append(event["path"])
                yield event
        except Exception as exc:
            logger.error(f"PhaseRunner error: {exc}", exc_info=True)
            yield {"type": "error", "error": str(exc)}
            return

        # ── 3. Final commit summary ───────────────────────────────────────────
        self.session_manager.add_message(session_id, ChatMessage(
            role="assistant",
            content=f"[PhasedRun] {request.task} — {len(phases)} phase(s) complete",
        ))
        report = getattr(runner, "last_verification", None)
        yield {
            "type": "phased_done",
            "total_phases": len(phases),
            "files_written": files_written,
            "verification": (
                self._verification_summary(report).model_dump() if report else None
            ),
        }

    @staticmethod
    def _verification_summary(report) -> VerificationSummary:
        """Convert a verifier VerificationReport into the response model."""
        return VerificationSummary(
            final_status=report.final_status,
            checks_run=report.checks_run,
            passed=report.passed,
            repair_attempted=report.repair_attempted,
            repair_attempts=report.repair_attempts,
            last_failure_summary=report.last_failure_summary,
        )

    def _agent_result_to_steps(self, result, total_ms: int) -> list[AutoRunStep]:
        """Convert AgentLoop tool call log into AutoRunStep cards."""
        if not result.tool_calls:
            return [AutoRunStep(
                step_name="agent",
                status="success" if result.success else "failed",
                message=result.summary,
                duration_ms=total_ms,
            )]

        # Group by phase
        phases: dict[str, list] = {"explore": [], "implement": [], "test": [], "finish": []}
        for tc in result.tool_calls:
            if tc.tool_name in ("read_file", "list_dir", "search_code"):
                phases["explore"].append(tc)
            elif tc.tool_name == "write_file":
                phases["implement"].append(tc)
            elif tc.tool_name == "run_command":
                phases["test"].append(tc)
            else:
                phases["finish"].append(tc)

        steps: list[AutoRunStep] = []
        for phase, calls in phases.items():
            if not calls:
                continue
            dur = sum(c.duration_ms for c in calls)
            if phase == "explore":
                msg = f"Read {len(calls)} file(s)/search(es)"
            elif phase == "implement":
                names = ", ".join(c.tool_input.get("path", "?") for c in calls)
                msg = f"Wrote: {names}"
            elif phase == "test":
                cmds = [c.tool_input.get("command", "?")[:60] for c in calls]
                exits = [c.result[:30] for c in calls]
                msg = f"Ran {len(calls)} command(s): {'; '.join(cmds)}"
                # Mark failed if any command exited non-zero
                status = "failed" if any("[exit " in e and "[exit 0]" not in e for e in exits) else "success"
                steps.append(AutoRunStep(step_name=phase, status=status, message=msg, duration_ms=dur))
                continue
            else:
                msg = result.summary
            steps.append(AutoRunStep(step_name=phase, status="success", message=msg, duration_ms=dur))

        if not steps:
            steps.append(AutoRunStep(
                step_name="agent",
                status="success" if result.success else "failed",
                message=result.summary,
                duration_ms=total_ms,
            ))
        return steps

    def _commit_agent_changes(
        self, session_id: str, task: str, change_set, repo_path: str
    ) -> Optional[ExecutionResultCard]:
        """
        Gate the agent's ChangeSet through the core validation/governance
        pipeline, then commit ONLY the staged files. Never uses `git add -A`.
        Returns a Broken card (no commit) when the gate blocks the change.
        """
        from app.interactive.change_set import evaluate_change_set

        if change_set is None or change_set.is_empty():
            return None

        gate = evaluate_change_set(change_set, description=task, mode="CRITICAL")
        if not gate.passed:
            reverted = False
            try:
                change_set.revert(repo_path)
                reverted = True
                logger.info(f"Reverted blocked ChangeSet paths: {change_set.paths}")
            except Exception as exc:
                logger.error(f"Failed to revert blocked ChangeSet: {exc}", exc_info=True)
            card = ExecutionResultCard(
                status="Broken", mode="CRITICAL",
                files_changed=change_set.paths,
                lines_changed=gate.lines_changed,
                validation_passed=False,
                error="; ".join(gate.errors),
                reverted=reverted,
            )
            self.session_manager.set_last_execution(session_id, card)
            logger.warning(f"ChangeSet blocked for session {session_id}: {gate.errors}")
            return card

        try:
            subprocess.run(["git", "add", "--", *change_set.paths],
                           cwd=repo_path, check=True, capture_output=True, timeout=15)
            msg = f"agent: {task[:72]}"
            proc = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=repo_path, capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0:
                sha_proc = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=repo_path, capture_output=True, text=True
                )
                sha = sha_proc.stdout.strip()
                card = ExecutionResultCard(
                    status="Working", mode="CRITICAL",
                    commit_sha=sha,
                    files_changed=change_set.paths,
                    lines_changed=gate.lines_changed,
                    validation_passed=True,
                )
                self.session_manager.set_last_execution(session_id, card)
                logger.info(f"AgentLoop commit {sha} for session {session_id}")
                return card
            else:
                # Nothing to commit is not an error
                logger.info(f"git commit skipped: {proc.stdout.strip() or proc.stderr.strip()}")
        except Exception as exc:
            logger.warning(f"Could not commit agent changes: {exc}")
        return None


# Global orchestrator instance
_orchestrator: Optional[InteractiveOrchestrator] = None


def get_orchestrator(engine: Optional[Engine] = None) -> InteractiveOrchestrator:
    """Get global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        if engine is None:
            raise ValueError("Engine required for first initialization")
        _orchestrator = InteractiveOrchestrator(engine)
    return _orchestrator

