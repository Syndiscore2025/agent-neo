"""
AGENT NEO - Agentic ReAct Loop
Tool-calling agent that mirrors Augment's flow:
  observe → think → act (tool) → observe → … → finish
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.interactive.tools import ToolExecutor, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15


@dataclass
class ToolCall:
    tool_name: str
    tool_input: dict
    result: str = ""
    duration_ms: int = 0


@dataclass
class AgentResult:
    success: bool
    summary: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """You are Agent NEO, an autonomous coding assistant.
You have access to real tools: read_file, write_file, list_dir, run_command, search_code, finish.

Guidelines:
1. ALWAYS read a file before modifying it so you write the full correct content.
2. Use search_code to discover relevant code before writing.
3. Use list_dir to explore unfamiliar directories.
4. After writing files, run tests or a linter with run_command to verify.
5. If tests fail, read the error output carefully, fix the code, and run tests again.
6. When done (or no further progress is possible), call finish with a clear summary.
7. Never call git push. Never delete files unless explicitly instructed.
8. Write complete file contents — never use placeholders like '# ... rest unchanged'.
"""


class AgentLoop:
    """
    ReAct-style agentic loop.

    Each iteration:
      1. Ask the LLM (with tools) what to do next
      2. Execute every tool call it requests
      3. Feed results back as user messages
      4. Repeat until the model calls `finish` or MAX_ITERATIONS reached
    """

    def __init__(self, model_router, repo_path: str):
        self.model_router = model_router
        self.repo_path = repo_path

    async def run(self, task: str, context: dict) -> AgentResult:
        executor = ToolExecutor(self.repo_path)
        tool_calls_log: list[ToolCall] = []

        # Build initial user message
        user_content = self._build_task_message(task, context)
        messages: list[dict] = [{"role": "user", "content": user_content}]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"AgentLoop iteration {iteration + 1}/{MAX_ITERATIONS}")

            try:
                llm_resp = await self.model_router.generate_with_tools(
                    system=_SYSTEM,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    max_tokens=4096,
                )
            except Exception as exc:
                logger.error(f"LLM call failed at iteration {iteration}: {exc}")
                return AgentResult(
                    success=False,
                    summary=f"LLM error at iteration {iteration + 1}: {exc}",
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                    error=str(exc),
                )

            tool_calls: list[dict] = llm_resp.get("tool_calls", [])

            # No tool calls → model is done (text-only response)
            if not tool_calls:
                return AgentResult(
                    success=True,
                    summary=llm_resp.get("text", "Task complete."),
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                )

            # Append assistant turn (raw content blocks)
            messages.append({"role": "assistant", "content": llm_resp["raw_content"]})

            # Execute each tool call and collect results
            tool_results = []
            finished = False
            finish_result: Optional[AgentResult] = None

            for tc in tool_calls:
                t0 = time.monotonic()
                name = tc["name"]
                inp = tc["input"]

                logger.info(f"  → tool={name} input_keys={list(inp.keys())}")
                result_text = executor.execute(name, inp)
                dur = int((time.monotonic() - t0) * 1000)

                call = ToolCall(tool_name=name, tool_input=inp, result=result_text, duration_ms=dur)
                tool_calls_log.append(call)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_text,
                })

                if name == "finish":
                    finished = True
                    finish_result = AgentResult(
                        success=bool(inp.get("success", True)),
                        summary=inp.get("summary", result_text),
                        tool_calls=tool_calls_log,
                        files_written=executor.files_written,
                    )

            # Feed results back into conversation
            messages.append({"role": "user", "content": tool_results})

            if finished and finish_result:
                return finish_result

        # Exceeded max iterations
        return AgentResult(
            success=False,
            summary=f"Reached max iterations ({MAX_ITERATIONS}). Task may be incomplete.",
            tool_calls=tool_calls_log,
            files_written=executor.files_written,
            error="max_iterations_exceeded",
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_task_message(self, task: str, context: dict) -> str:
        parts = [f"Task: {task}"]
        if context.get("current_file"):
            parts.append(f"Active file in editor: {context['current_file']}")
        if context.get("selected_code"):
            parts.append(f"Selected code:\n```\n{context['selected_code']}\n```")
        if context.get("repo_summary"):
            s = context["repo_summary"]
            parts.append(
                f"Repo: {s.get('total_files', '?')} files | "
                f"langs: {', '.join(s.get('languages', []))}"
            )
        return "\n\n".join(parts)

