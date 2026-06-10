"""
AGENT NEO - Agentic ReAct Loop
Tool-calling agent that mirrors Augment's flow:
  observe → think → act (tool) → observe → … → finish
"""
import asyncio
import difflib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from app.interactive.change_set import ChangeSet
from app.interactive.tools import (
    ToolExecutor, TOOL_SCHEMAS, get_filtered_schemas, get_integration_schemas,
)

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
    change_set: Optional[ChangeSet] = None


# ── Base system prompt ────────────────────────────────────────────────────────
_BASE_SYSTEM = """You are Agent NEO — an autonomous AI coding agent embedded in the developer's IDE.

You have real tools: read_file, write_file, list_dir, run_command, search_code, web_search, semantic_search, finish.

EXECUTION RULES (non-negotiable):
1. START WORKING IMMEDIATELY. Never say "Let me know how to proceed" or ask permission.
2. ALWAYS read a file before modifying it — write the complete, correct content.
3. Use search_code or semantic_search to find relevant code before writing anything.
4. Use list_dir to explore unknown directories.
5. After writing files, verify with run_command (tests, linter, build).
6. Fix failures: read error output → fix code → re-run → repeat until clean.
7. Call finish() only when all work is done or truly blocked, with a factual summary.
8. Never run git push. Never delete files unless explicitly told to.
9. Write COMPLETE file contents — zero placeholders like '# ... rest unchanged'.
10. Call multiple independent tools in one response — they run in parallel.
11. Never narrate what you are about to do. Just do it.
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

    def __init__(self, model_router, repo_path: str, model: Optional[str] = None):
        self.model_router = model_router
        self.repo_path = repo_path
        self.model = model
        self.last_change_set: Optional[ChangeSet] = None

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
        self.last_change_set = executor.change_set
        tool_calls_log: list[ToolCall] = []
        system = system_override or self._build_system()
        base_tools = get_filtered_schemas(tool_subset) if tool_subset else TOOL_SCHEMAS
        tools = base_tools + get_integration_schemas()
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
                    model=self.model,
                )
            except Exception as exc:
                logger.error(f"LLM call failed at iteration {iteration}: {exc}")
                return AgentResult(
                    success=False,
                    summary=f"LLM error at iteration {iteration + 1}/{limit}: {exc}",
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                    error=str(exc),
                    change_set=executor.change_set,
                )

            tool_calls: list[dict] = llm_resp.get("tool_calls", [])

            if not tool_calls:
                return AgentResult(
                    success=True,
                    summary=llm_resp.get("text", "Task complete."),
                    tool_calls=tool_calls_log,
                    files_written=executor.files_written,
                    change_set=executor.change_set,
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
                    change_set=executor.change_set,
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
            change_set=executor.change_set,
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
        self.last_change_set = executor.change_set
        tool_calls_log: list[ToolCall] = []
        system = system_override or self._build_system()
        base_tools = get_filtered_schemas(tool_subset) if tool_subset else TOOL_SCHEMAS
        tools = base_tools + get_integration_schemas()
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
                model=self.model,
            ):
                ctype = chunk.get("type")
                if ctype == "text":
                    text_buf += chunk["content"]
                    yield {"type": "text", "content": chunk["content"]}
                elif ctype == "tool_start":
                    yield {"type": "tool_start", "tool": chunk["tool"]}
                elif ctype == "tool_ready":
                    tc_info = {
                        "id": chunk["id"],
                        "name": chunk["tool"],
                        "input": chunk["input"],
                    }
                    pending_tool_calls.append(tc_info)
                    # Emit a richer tool_start now that we have the full input
                    rich_start: dict = {"type": "tool_start", "tool": chunk["tool"]}
                    inp = chunk["input"]
                    if chunk["tool"] in ("read_file", "write_file", "list_dir", "delete_file"):
                        if inp.get("path"):
                            rich_start["path"] = inp["path"].lstrip("/\\")
                    elif chunk["tool"] == "rename_file":
                        if inp.get("old_path"):
                            rich_start["path"] = inp["old_path"].lstrip("/\\")
                    elif chunk["tool"] == "run_command":
                        if inp.get("command"):
                            rich_start["command"] = inp["command"]
                    elif chunk["tool"] in ("search_code", "semantic_search"):
                        rich_start["query"] = inp.get("pattern") or inp.get("query", "")
                    yield rich_start
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

            # Pre-execution: snapshot old file content for write_file diffs
            pre_content: dict[str, str] = {}
            for tc in exec_calls:
                if tc["name"] == "write_file" and tc["input"].get("path"):
                    rel = tc["input"]["path"].lstrip("/\\")
                    old_path = executor.repo_path / rel
                    try:
                        pre_content[tc["id"]] = old_path.read_text(encoding="utf-8", errors="replace") if old_path.exists() else ""
                    except Exception:
                        pre_content[tc["id"]] = ""

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
                inp = tc["input"]
                if tc["name"] == "write_file" and inp.get("path"):
                    rel = inp["path"].lstrip("/\\")
                    event["path"] = rel
                    new_content = inp.get("content", "")
                    old_content = pre_content.get(tc["id"], "")
                    old_lines = old_content.splitlines()
                    new_lines = new_content.splitlines()
                    added = removed = 0
                    for line in difflib.unified_diff(old_lines, new_lines):
                        if line.startswith("+") and not line.startswith("+++"):
                            added += 1
                        elif line.startswith("-") and not line.startswith("---"):
                            removed += 1
                    event["lines_added"] = added
                    event["lines_removed"] = removed
                    event["total_lines"] = len(new_lines)
                elif tc["name"] == "read_file" and inp.get("path"):
                    event["path"] = inp["path"].lstrip("/\\")
                    event["lines_read"] = len(result_text.splitlines())
                elif tc["name"] == "run_command" and inp.get("command"):
                    event["command"] = inp["command"]
                elif tc["name"] == "list_dir":
                    event["path"] = inp.get("path", ".").lstrip("/\\") or "."
                elif tc["name"] == "delete_file" and inp.get("path"):
                    event["path"] = inp["path"].lstrip("/\\")
                    event["operation"] = "delete"
                elif tc["name"] == "rename_file":
                    if inp.get("new_path"):
                        event["path"] = inp["new_path"].lstrip("/\\")
                    if inp.get("old_path"):
                        event["renamed_from"] = inp["old_path"].lstrip("/\\")
                    event["operation"] = "rename"
                elif tc["name"] in ("search_code", "semantic_search"):
                    event["query"] = inp.get("pattern") or inp.get("query", "")
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
        # Task-aware context pack: files selected by the context engine, with reasons
        pack_files = context.get("context_files_with_reasons") or []
        if pack_files:
            file_lines = "\n".join(
                f"  • {f.get('path', '?')} — {f.get('reason', '')}"
                for f in pack_files[:15]
            )
            parts.append(
                f"RELEVANT FILES (selected by the context engine, with reasons):\n{file_lines}"
            )
        # Inject VS Code diagnostics (errors / warnings from IDE)
        diagnostics = context.get("diagnostics") or []
        if diagnostics:
            diag_lines = "\n".join(f"  • {d}" for d in diagnostics[:20])
            parts.append(
                f"CURRENT IDE DIAGNOSTICS (errors/warnings you should fix):\n{diag_lines}"
            )
        return "\n\n".join(parts)

