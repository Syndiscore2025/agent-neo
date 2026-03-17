"""
AGENT NEO - Interactive Orchestrator
Main orchestration logic for interactive chat workflow.
"""

import logging
from typing import Optional
from datetime import datetime

from app.interactive.contracts import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ApprovalRequest,
    ApprovalResponse,
    ActionType
)
from app.interactive.session_manager import get_session_manager
from app.interactive.model_router import get_model_router
from app.interactive.context_engine import get_context_engine
from app.interactive.action_planner import get_action_planner
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

        # Build enriched prompt with context and intent
        enriched_prompt = self._build_enriched_prompt(
            user_message=request.message,
            context=context,
            session=session,
            intent=intent
        )

        # Generate model response
        logger.info(f"Generating response for session {session_id} (intent: {intent})")
        model_response = await self.model_router.generate_response(
            prompt=enriched_prompt,
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
        intent: str = "conversational"
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

        # Add system context
        parts.append("You are Agent NEO, an AI coding assistant with access to a repository.")
        parts.append("You help with code explanation, refactoring, testing, and modifications.")
        parts.append("")

        # Add diff generation instructions for modification intents
        if intent in ["modify", "generate_tests"]:
            parts.append("IMPORTANT: When making code changes, provide your response in this format:")
            parts.append("1. Brief explanation of what you're changing and why")
            parts.append("2. The changes in unified diff format inside a ```diff code block")
            parts.append("")
            parts.append("Diff format example:")
            parts.append("```diff")
            parts.append("--- a/path/to/file.py")
            parts.append("+++ b/path/to/file.py")
            parts.append("@@ -10,3 +10,4 @@")
            parts.append(" unchanged line")
            parts.append("-old line")
            parts.append("+new line")
            parts.append("+added line")
            parts.append("```")
            parts.append("")
        else:
            parts.append("When proposing code changes, explain what you're doing and why.")
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

            # Format success message
            message = f"✓ Changes applied successfully!\n"
            message += f"Status: {execution_result.status}\n"
            message += f"Mode: {execution_result.mode}\n"

            if execution_result.files_changed:
                message += f"Files changed: {len(execution_result.files_changed)}\n"

            if execution_result.pushed:
                message += f"Changes pushed to remote: {execution_result.pushed}\n"

            logger.info(
                f"Diff executed successfully for session {request.session_id} | "
                f"status={execution_result.status} | "
                f"mode={execution_result.mode}"
            )

            return ApprovalResponse(
                session_id=request.session_id,
                approved=True,
                message=message,
                execution_result={
                    "status": execution_result.status,
                    "mode": execution_result.mode,
                    "files_changed": execution_result.files_changed,
                    "pushed": execution_result.pushed,
                    "logs": execution_result.logs[-10:] if execution_result.logs else []  # Last 10 logs
                }
            )

        except Exception as e:
            logger.error(f"Execution failed for session {request.session_id}: {e}", exc_info=True)

            # Clear proposed diff even on failure
            self.session_manager.clear_proposed_diff(request.session_id)

            return ApprovalResponse(
                session_id=request.session_id,
                approved=True,
                message=f"✗ Execution failed: {str(e)}",
                execution_result={
                    "status": "failed",
                    "error": str(e)
                }
            )


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

