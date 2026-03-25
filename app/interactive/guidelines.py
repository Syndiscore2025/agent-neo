"""
AGENT NEO - Guidelines Loader
Reads project-specific .neo rule files and injects them into the system prompt.

Files searched (in order of specificity):
  <repo_root>/.neo               — top-level rules
  <repo_root>/.neo.md            — markdown rules
  <repo_root>/AGENT.md           — community convention (like Claude's CLAUDE.md)
  <repo_root>/app/kernel/KERNEL.md
  <repo_root>/app/kernel/GUARDRAILS.md
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Files to look for, in priority order (all that exist are concatenated)
_GUIDELINE_FILES = [
    ".neo",
    ".neo.md",
    "AGENT.md",
    "app/kernel/KERNEL.md",
    "app/kernel/GUARDRAILS.md",
]

_MAX_BYTES = 8_000   # cap total injected guidelines to avoid filling context


def load_guidelines(repo_path: str) -> str:
    """
    Load all guideline files found in the repo and return them as a single
    formatted block suitable for injection into a system prompt.

    Returns an empty string if no guideline files are found.
    """
    root = Path(repo_path).resolve()
    sections: list[str] = []
    total_bytes = 0

    for rel in _GUIDELINE_FILES:
        fpath = root / rel
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            chunk = f"## Rules from {rel}\n{text}\n"
            if total_bytes + len(chunk) > _MAX_BYTES:
                # Truncate to fit
                remaining = _MAX_BYTES - total_bytes
                chunk = chunk[:remaining] + "\n… (truncated)"
                sections.append(chunk)
                total_bytes += len(chunk)
                break
            sections.append(chunk)
            total_bytes += len(chunk)
            logger.debug(f"Loaded guidelines from {rel} ({len(text)} chars)")
        except Exception as exc:
            logger.warning(f"Could not read guideline file {rel}: {exc}")

    if not sections:
        return ""

    header = "=== PROJECT GUIDELINES (from .neo / AGENT.md) ===\n"
    footer = "=== END PROJECT GUIDELINES ===\n"
    return header + "\n".join(sections) + footer


def build_system_prompt(base_prompt: str, repo_path: Optional[str]) -> str:
    """
    Prepend project guidelines to the base system prompt.
    Safe to call even if no guidelines exist.
    """
    if not repo_path:
        return base_prompt
    guidelines = load_guidelines(repo_path)
    if not guidelines:
        return base_prompt
    return f"{guidelines}\n{base_prompt}"

