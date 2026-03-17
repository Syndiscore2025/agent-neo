"""
AGENT NEO - Action Planner
Converts model output into structured actions.
"""

import logging
import re
from typing import Optional, Tuple, List
from app.interactive.contracts import ActionType, DiffProposal

logger = logging.getLogger(__name__)


class ActionPlanner:
    """
    Plans actions based on user intent and model responses.
    
    Separates conversational responses from execution actions.
    """
    
    def __init__(self):
        """Initialize action planner."""
        pass
    
    def detect_intent(self, user_message: str) -> str:
        """
        Detect user intent from message.

        Args:
            user_message: User's message

        Returns:
            Intent type (conversational, modify, explain, etc.)
        """
        message_lower = user_message.lower()

        # Modification keywords
        modify_keywords = [
            "add", "create", "modify", "change", "update", "fix", "refactor",
            "implement", "write", "build", "make", "edit", "delete", "remove",
            "rename", "move", "replace", "insert", "append", "prepend"
        ]

        # Explanation keywords
        explain_keywords = [
            "explain", "what", "how", "why", "show", "tell", "describe",
            "understand", "clarify", "meaning", "purpose"
        ]

        # Test generation keywords
        test_keywords = ["test", "tests", "testing", "unit test", "integration test"]

        if any(word in message_lower for word in modify_keywords):
            return "modify"
        elif any(word in message_lower for word in test_keywords):
            return "generate_tests"
        elif any(word in message_lower for word in explain_keywords):
            return "explain"
        else:
            return "conversational"
    
    def parse_model_response(
        self,
        response: str,
        intent: str
    ) -> Tuple[str, Optional[str]]:
        """
        Parse model response into action type and content.

        Args:
            response: Model's response
            intent: Detected intent

        Returns:
            Tuple of (action_type, diff_content)
        """
        # Check if response contains code blocks or diffs
        has_code_block = "```" in response
        has_diff = "```diff" in response or "--- a/" in response or "+++ b/" in response

        if intent in ["modify", "generate_tests"]:
            if has_diff:
                # Extract diff from response
                diff = self._extract_diff_from_response(response)
                if diff:
                    return ActionType.DIFF_PROPOSAL, diff
            elif has_code_block:
                # Try to convert code blocks to diff
                diff = self._convert_code_blocks_to_diff(response)
                if diff:
                    return ActionType.DIFF_PROPOSAL, diff

        return ActionType.CONVERSATIONAL, None

    def _extract_diff_from_response(self, response: str) -> Optional[str]:
        """
        Extract unified diff from model response.

        Args:
            response: Model response

        Returns:
            Extracted diff or None
        """
        # Look for diff code blocks
        diff_pattern = r'```diff\n(.*?)\n```'
        matches = re.findall(diff_pattern, response, re.DOTALL)

        if matches:
            return matches[0]

        # Look for raw unified diff format
        if "--- a/" in response and "+++ b/" in response:
            # Extract everything that looks like a diff
            lines = response.split('\n')
            diff_lines = []
            in_diff = False

            for line in lines:
                if line.startswith('--- a/') or line.startswith('diff --git'):
                    in_diff = True
                if in_diff:
                    diff_lines.append(line)
                    # Stop at next markdown block or end
                    if line.startswith('```') and len(diff_lines) > 1:
                        break

            if diff_lines:
                return '\n'.join(diff_lines)

        return None

    def _convert_code_blocks_to_diff(self, response: str) -> Optional[str]:
        """
        Convert code blocks in response to a diff format.

        This is a simplified approach - we'll ask the LLM to provide
        the file path and generate a simple replacement diff.

        Args:
            response: Model response

        Returns:
            Generated diff or None
        """
        # Extract code blocks
        code_pattern = r'```(\w+)?\n(.*?)\n```'
        matches = re.findall(code_pattern, response, re.DOTALL)

        if not matches:
            return None

        # For now, we'll return None and let the orchestrator handle this
        # In a full implementation, we'd need file context to generate proper diffs
        logger.info("Found code blocks but cannot convert to diff without file context")
        return None
    
    def create_diff_proposal(
        self,
        diff: str,
        summary: str
    ) -> DiffProposal:
        """
        Create a diff proposal from generated diff.
        
        Args:
            diff: Unified diff string
            summary: Human-readable summary
            
        Returns:
            DiffProposal object
            
        TODO: Implement in SLICE 4
        """
        from app.modules.diff_generator import extract_changed_files, count_diff_changes
        
        files_changed = extract_changed_files(diff)
        additions, deletions = count_diff_changes(diff)
        
        return DiffProposal(
            diff=diff,
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            summary=summary
        )
    
    def should_require_approval(self, action_type: str) -> bool:
        """
        Determine if action requires user approval.
        
        Args:
            action_type: Type of action
            
        Returns:
            True if approval required
        """
        # All code modifications require approval
        return action_type == ActionType.DIFF_PROPOSAL
    
    def plan_action(
        self,
        user_message: str,
        model_response: str,
        context: dict
    ) -> dict:
        """
        Plan action based on user message and model response.
        
        Args:
            user_message: User's message
            model_response: Model's response
            context: Current context
            
        Returns:
            Action plan dictionary
            
        TODO: Implement full planning logic in SLICE 4
        """
        intent = self.detect_intent(user_message)
        action_type, diff_content = self.parse_model_response(model_response, intent)
        
        plan = {
            "intent": intent,
            "action_type": action_type,
            "requires_approval": self.should_require_approval(action_type),
            "diff": diff_content,
            "response": model_response
        }
        
        return plan


# Global action planner instance
_action_planner: Optional[ActionPlanner] = None


def get_action_planner() -> ActionPlanner:
    """Get global action planner instance."""
    global _action_planner
    if _action_planner is None:
        _action_planner = ActionPlanner()
    return _action_planner

