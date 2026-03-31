"""
AGENT NEO - Agentic ReAct Loop
Tool-calling agent that mirrors Augment's flow:
  observe → think → act (tool) → observe → … → finish
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from app.interactive.tools import ToolExecutor, TOOL_SCHEMAS, get_filtered_schemas

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


# ── Base system prompt ────────────────────────────────────────────────────────
_BASE_SYSTEM = """You are Agent NEO, an autonomous coding assistant.
You have access to real tools: read_file, write_file, list_dir, run_command, search_code, web_search, semantic_search, finish.

Guidelines:
1. ALWAYS read a file before modifying it so you write the full correct content.
2. Use semantic_search or search_code to discover relevant code before writing.
3. Use list_dir to explore unfamiliar directories.
4. After writing files, run tests or a linter with run_command to verify.
5. If tests fail, read the error output carefully, fix the code, and run tests again.
6. When done (or no further progress is possible), call finish with a clear summary.
7. Never call git push. Never delete files unless explicitly instructed.
8. Write complete file contents — never use placeholders like '# ... rest unchanged'.
9. You may call multiple independent tools in a single response — they will execute in parallel.
"""


class AgentLoop:
    """
    ReAct-style agentic loop.

    Each iteration:
      1. Ask the LLM (with tools) what to do next
      2. Execute every tool call it requests (in parallel when safe)
      3. Feed results back as user messages
      4. Repeat until the model calls `finish` or MAX_ITERATIONS reached
    """

    def __init__(self, model_router, repo_path: str):
        self.model_router = model_router
        self.repo_path = repo_path

    def _build_system(self) -> str:
        """Build system prompt: base rules + project guidelines."""
        try:
            from app.interactive.guidelines import build_system_prompt
            return build_system_prompt(_BASE_SYSTEM, self.repo_path)
        except Exception:
            return _BASE_SYSTEM

    async def run(
        self,
        task: str,
        context: dict,
        system_override: Optional[str] = None,
        tool_subset: Optional[list[str]] = None,
        max_iterations_override: Optional[int] = None,
    ) -> AgentResult:
        executor = ToolExecutor(self.repo_path)
        tool_calls_log: list[ToolCall] = []
        system = system_override or self._build_system()
        tools = get_filtered_schemas(tool_subset) if tool_subset else TOOL_SCHEMAS
        limit = max_iterations_override or MAX_ITERATIONS

        user_content = self._build_task_message(task, context)
        messages: list[dict] = [{"role": "user", "content": user_content}]

        for iteration in range(limit):
            logger.info(f"AgentLoop iteration {iteration + 1}/{limit}")

            try:
                llm_resp = await self.model_router.generate_with_tools(
                    system=system,
                    messages=messages,
                    tools=tools,
                    max_tokens=4096,
                )
            except Exception as exc:
                logger.error(f"LLM call failed at iteration {iteration}: {exc}")
                return AgentResult(
                    success=False,
                    summary=f"LLM error at iteration {iteration + 1}/{limit}: {exc}",
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                    error=str(exc),
                )

            tool_calls: list[dict] = llm_resp.get("tool_calls", [])

            if not tool_calls:
                return AgentResult(
                    success=True,
                    summary=llm_resp.get("text", "Task complete."),
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                )

            messages.append({"role": "assistant", "content": llm_resp["raw_content"]})

            # ── Parallel execution: run all non-finish tool calls concurrently ──
            t0 = time.monotonic()
            finish_calls = [tc for tc in tool_calls if tc["name"] == "finish"]
            exec_calls = [tc for tc in tool_calls if tc["name"] != "finish"]

            if exec_calls:
                loop = asyncio.get_event_loop()
                results_text = await asyncio.gather(*[
                    loop.run_in_executor(None, executor.execute, tc["name"], tc["input"])
                    for tc in exec_calls
                ])
            else:
                results_text = []

            dur_each = int((time.monotonic() - t0) * 1000 / max(len(exec_calls), 1))
            tool_results = []

            for tc, result_text in zip(exec_calls, results_text):
                logger.info(f"  → tool={tc['name']} input_keys={list(tc['input'].keys())}")
                call = ToolCall(tool_name=tc["name"], tool_input=tc["input"],
                                result=result_text, duration_ms=dur_each)
                tool_calls_log.append(call)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_text,
                })

            # Handle finish calls
            finished = False
            finish_result: Optional[AgentResult] = None
            for tc in finish_calls:
                inp = tc["input"]
                result_text = f"[finish] {inp.get('summary', '')}"
                call = ToolCall(tool_name="finish", tool_input=inp,
                                result=result_text, duration_ms=0)
                tool_calls_log.append(call)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_text,
                })
                finished = True
                finish_result = AgentResult(
                    success=bool(inp.get("success", True)),
                    summary=inp.get("summary", result_text),
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                )

            messages.append({"role": "user", "content": tool_results})

            if finished and finish_result:
                return finish_result

        return AgentResult(
            success=False,
            summary=f"Reached max iterations ({limit}). Task may be incomplete.",
            tool_calls=tool_calls_log,
            files_written=executor.files_written,
            error="max_iterations_exceeded",
        )

    async def run_stream(
        self,
        task: str,
        context: dict,
        system_override: Optional[str] = None,
        tool_subset: Optional[list[str]] = None,
        max_iterations_override: Optional[int] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming ReAct loop — yields SSE-compatible dicts at each step.
        Compatible with StreamEvent schema in contracts.py.
        """
        executor = ToolExecutor(self.repo_path)
        tool_calls_log: list[ToolCall] = []
        system = system_override or self._build_system()
        tools = get_filtered_schemas(tool_subset) if tool_subset else TOOL_SCHEMAS
        limit = max_iterations_override or MAX_ITERATIONS

        user_content = self._build_task_message(task, context)
        messages: list[dict] = [{"role": "user", "content": user_content}]

        for iteration in range(limit):
            pending_tool_calls: list[dict] = []  # {"id", "name", "input"}
            raw_content_blocks: list[dict] = []
            text_buf = ""

            # Stream the LLM response
            async for chunk in self.model_router.stream_with_tools(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=4096,
            ):
                ctype = chunk.get("type")
                if ctype == "text":
                    text_buf += chunk["content"]
                    yield {"type": "text", "content": chunk["content"]}
                elif ctype == "tool_start":
                    yield {"type": "tool_start", "tool": chunk["tool"]}
                elif ctype == "tool_ready":
                    pending_tool_calls.append({
                        "id": chunk["id"],
                        "name": chunk["tool"],
                        "input": chunk["input"],
                    })
                elif ctype == "error":
                    yield {"type": "error", "error": chunk["error"]}
                    return
                elif ctype == "done":
                    break

            # Build raw_content for multi-turn
            if text_buf:
                raw_content_blocks.append({"type": "text", "text": text_buf})
            for tc in pending_tool_calls:
                raw_content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })

            if not pending_tool_calls:
                # Text-only → done
                yield {"type": "finish", "success": True, "summary": text_buf or "Task complete."}
                return

            messages.append({"role": "assistant", "content": raw_content_blocks})

            # Execute tools in parallel (skip finish)
            finish_calls = [tc for tc in pending_tool_calls if tc["name"] == "finish"]
            exec_calls = [tc for tc in pending_tool_calls if tc["name"] != "finish"]

            t0 = time.monotonic()
            if exec_calls:
                loop = asyncio.get_event_loop()
                results_text = list(await asyncio.gather(*[
                    loop.run_in_executor(None, executor.execute, tc["name"], tc["input"])
                    for tc in exec_calls
                ]))
            else:
                results_text = []

            dur_each = int((time.monotonic() - t0) * 1000 / max(len(exec_calls), 1))
            tool_results = []

            for tc, result_text in zip(exec_calls, results_text):
                call = ToolCall(tool_name=tc["name"], tool_input=tc["input"],
                                result=result_text, duration_ms=dur_each)
                tool_calls_log.append(call)
                tool_results.append({"type": "tool_result", "tool_use_id": tc["id"], "content": result_text})
                event: dict = {
                    "type": "tool_end",
                    "tool": tc["name"],
                    "result": result_text[:400],
                    "duration_ms": dur_each,
                }
                # For write_file, include the path so the extension can open it
                if tc["name"] == "write_file" and tc["input"].get("path"):
                    event["path"] = tc["input"]["path"].lstrip("/\\")
                yield event

            for tc in finish_calls:
                inp = tc["input"]
                tool_results.append({"type": "tool_result", "tool_use_id": tc["id"],
                                     "content": f"[finish] {inp.get('summary', '')}"})
                yield {
                    "type": "finish",
                    "success": bool(inp.get("success", True)),
                    "summary": inp.get("summary", ""),
                    "files": executor.files_written,
                }
                return

            messages.append({"role": "user", "content": tool_results})

        yield {"type": "finish", "success": False,
               "summary": f"Reached max iterations ({limit}).",
               "files": executor.files_written}

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
        # Inject VS Code diagnostics (errors / warnings from IDE)
        diagnostics = context.get("diagnostics") or []
        if diagnostics:
            diag_lines = "\n".join(f"  • {d}" for d in diagnostics[:20])
            parts.append(
                f"CURRENT IDE DIAGNOSTICS (errors/warnings you should fix):\n{diag_lines}"
            )
        return "\n\n".join(parts)

