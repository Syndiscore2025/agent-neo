"""
AGENT NEO - Task Planner
Decomposes a user task into a sequence of phases, each assigned to a specialist.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_PLANNER_PROMPT = """\
You are Agent NEO's planning system. Given a coding task, decompose it into 2-6 phases.

Respond with ONLY valid JSON — no markdown fences, no extra text:
{{
  "phases": [
    {{
      "id": "phase_1",
      "name": "Short phase name",
      "description": "Detailed instructions for the specialist",
      "specialist": "explorer|writer|tester|reviewer",
      "dependencies": [],
      "checkpoint_cmd": null
    }}
  ]
}}

Rules:
- Always start with an "explorer" phase (unless the task is trivially small).
- "writer" phases implement code using explorer findings.
- "tester" phases run and fix tests — add one if code is being changed.
- "reviewer" phases check for bugs/security — optional, add for complex tasks.
- "dependencies": list of phase IDs that must complete before this one starts.
- "checkpoint_cmd": optional shell command to verify the phase (e.g. "python -m pytest").
  Every phase that edits files is automatically verified by the system after it
  completes; set checkpoint_cmd only when a specific command should be used.
- Keep phases focused. Each phase does ONE clear thing.
- For small tasks (fix a typo, rename a variable), use 1-2 phases max.

Context:
{context}

Task: {task}

Respond with ONLY the JSON object:"""


@dataclass
class Phase:
    id: str
    name: str
    description: str
    specialist: str
    dependencies: list[str] = field(default_factory=list)
    checkpoint_cmd: Optional[str] = None


async def plan_task(model_router, task: str, context: dict) -> list[Phase]:
    """
    Call the LLM to decompose `task` into a list of Phase objects.
    Falls back to a single default phase if planning fails.
    """
    context_lines: list[str] = []
    if context.get("current_file"):
        context_lines.append(f"Active file: {context['current_file']}")
    if context.get("repo_summary"):
        s = context["repo_summary"]
        context_lines.append(
            f"Repo: {s.get('total_files', '?')} files, "
            f"langs: {', '.join(s.get('languages', []))}"
        )
    pack_files = context.get("context_files_with_reasons") or []
    if pack_files:
        context_lines.append("Relevant files (selected by the context engine):")
        for f in pack_files[:10]:
            context_lines.append(f"  - {f.get('path', '?')} — {f.get('reason', '')}")
    if context.get("service_graph_summary"):
        context_lines.append(
            f"Stack / service graph: {context['service_graph_summary']}"
        )
    context_str = "\n".join(context_lines) if context_lines else "No additional context."

    prompt = _PLANNER_PROMPT.format(context=context_str, task=task)

    try:
        raw = await model_router.generate_response(
            prompt=prompt, max_tokens=1500, temperature=0.2
        )
        # Strip markdown fences if the model adds them anyway
        raw = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\n?```$", "", raw.strip(), flags=re.MULTILINE)

        data = json.loads(raw)
        phases: list[Phase] = []
        for p in data.get("phases", []):
            phases.append(Phase(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                specialist=p.get("specialist", "writer"),
                dependencies=p.get("dependencies", []),
                checkpoint_cmd=p.get("checkpoint_cmd") or None,
            ))

        if phases:
            logger.info(
                f"Planner: {len(phases)} phase(s) — "
                f"{[ph.name for ph in phases]}"
            )
            return phases

    except Exception as exc:
        logger.warning(f"Planner failed ({exc}), falling back to single-phase")

    # Fallback: single writer phase
    return [Phase(
        id="phase_1",
        name="Execute task",
        description=task,
        specialist="writer",
        dependencies=[],
        checkpoint_cmd=None,
    )]

