"""
AGENT NEO - Context Engine
Gathers repository-aware context for chat interactions.
"""

import logging
import re
from typing import Optional, List, Dict, Set
from pathlib import Path

from app.modules.repo_context import (
    scan_repository,
    get_file_content,
    find_files_by_pattern,
    get_directory_structure
)
from app.interactive.contracts import (
    ChatContext,
    CommitInfo,
    ContextPack,
    FileContext,
    GitHistory,
    ServiceGraph,
    ServiceNode,
)

logger = logging.getLogger(__name__)


class ContextEngine:
    """
    Gathers and enriches context for chat interactions.

    For MVP: Simple file-based context gathering.
    No vector DB or embeddings yet.
    """

    def __init__(self, repo_path: str):
        """
        Initialize context engine.

        Args:
            repo_path: Path to repository
        """
        self.repo_path = Path(repo_path)
        self._repo_cache: Optional[Dict] = None
        self._file_cache: Dict[str, str] = {}

        # Configuration
        self.max_file_size = 100000  # 100KB
        self.max_context_lines = 500
        self.max_related_files = 5
        self.max_pack_files = 15
        self.max_primary_files = 5

    def gather_context(self, chat_context: Optional[ChatContext] = None) -> Dict:
        """
        Gather context for a chat interaction.

        Args:
            chat_context: Context from VS Code extension

        Returns:
            Enriched context dictionary
        """
        context = {
            "repo_path": str(self.repo_path),
            "current_file": None,
            "current_file_content": None,
            "selected_code": None,
            "related_files": [],
            "repo_summary": None
        }

        # Add VS Code context if provided
        if chat_context:
            context["current_file"] = chat_context.current_file
            context["current_file_content"] = chat_context.current_file_content
            context["selected_code"] = chat_context.selected_code
            context["language"] = chat_context.language

        # Get repository summary (cached)
        if self._repo_cache is None:
            try:
                repo_info = scan_repository(str(self.repo_path))
                self._repo_cache = {
                    "total_files": repo_info.get("total_files", 0),
                    "total_lines": repo_info.get("total_lines", 0),
                    "languages": repo_info.get("languages", []),
                    "has_tests": repo_info.get("has_tests", False)
                }
            except Exception as e:
                logger.warning(f"Failed to scan repository: {e}")
                self._repo_cache = {}

        context["repo_summary"] = self._repo_cache

        # Find related files if we have a current file
        if context.get("current_file"):
            context["related_files"] = self._find_related_files_smart(
                context["current_file"],
                context.get("current_file_content")
            )

        return context

    def build_context_pack(
        self,
        task_description: str,
        chat_context: Optional[ChatContext] = None,
    ) -> ContextPack:
        """
        Build a ranked, explainable set of files relevant to a task.

        Combines the shared RepoIndex (semantic/keyword search) with active-file
        heuristics (imports, test file, siblings). Every file carries a reason.
        Degrades to heuristics-only if the RepoIndex is unavailable.
        """
        candidates: List[FileContext] = []
        seen: Set = set()

        def add(path: str, reason: str, source: str,
                score: Optional[float] = None, repo: Optional[str] = None):
            norm = Path(path).as_posix()
            key = (repo or "", norm)
            if key in seen or len(candidates) >= self.max_pack_files:
                return
            seen.add(key)
            candidates.append(
                FileContext(path=norm, reason=reason, source=source, score=score, repo=repo)
            )

        current_file = chat_context.current_file if chat_context else None
        current_content = chat_context.current_file_content if chat_context else None

        # 1. Active file always leads
        if current_file:
            add(current_file, "active file in editor", "active_file")

            # 2. Imports of the active file
            if current_content:
                suffix = Path(current_file).suffix
                for imp in self._extract_imports(current_content, suffix)[:self.max_related_files]:
                    if (self.repo_path / imp).exists():
                        add(imp, f"imported by the active file ({Path(current_file).name})", "import")

            # 3. Likely test file
            test_file = self._find_test_file(current_file)
            if test_file:
                add(test_file, f"likely test file for {Path(current_file).name}", "test_file")

        # 4. Task-driven search across all managed repos (active repo leads)
        index_summary = None
        cross_repo = 0
        try:
            from app.modules.repo_index import get_repo_index, search_across_repos
            active_path = str(self.repo_path)
            for result in search_across_repos(task_description, k=12, active_path=active_path):
                meta = get_repo_index(result["repo_path"]).get_file_metadata(result["path"]) or {}
                is_active = result.get("is_active", True)
                repo_name = result.get("repo_name")
                if meta.get("is_convention"):
                    reason = f"convention file: {Path(result['path']).name} ({result['reason']})"
                    source = "convention"
                else:
                    reason = result["reason"]
                    source = "semantic" if result["reason"].startswith("semantic") else "keyword"
                if not is_active:
                    reason = f"[{repo_name}] {reason}"
                    source = "cross_repo"
                    cross_repo += 1
                add(result["path"], reason, source,
                    score=result.get("score"),
                    repo=None if is_active else repo_name)
            index_summary = get_repo_index(active_path).summarize()
        except Exception as exc:
            logger.warning(f"RepoIndex unavailable for context pack: {exc}")

        # 5. Same-directory siblings of the active file (lowest priority)
        if current_file:
            for sibling in self._find_files_in_same_directory(current_file):
                add(sibling, "same directory as active file", "sibling")

        primary = candidates[:self.max_primary_files]
        supporting = candidates[self.max_primary_files:]

        source_counts: Dict[str, int] = {}
        for fc in candidates:
            source_counts[fc.source] = source_counts.get(fc.source, 0) + 1
        breakdown = ", ".join(f"{n} {src}" for src, n in source_counts.items())
        summary = (
            f"Selected {len(candidates)} file(s) for task "
            f"'{task_description.strip()[:60]}'"
            + (f" ({breakdown})" if breakdown else "")
        )
        if cross_repo:
            summary += f" — incl. {cross_repo} from other managed repos"
        if index_summary and not index_summary.get("embeddings_available"):
            summary += " — keyword search (embeddings unavailable)"

        # 6. Coarse service/dependency graph (best-effort, never blocks a run)
        service_graph = self._build_service_graph()
        if service_graph and service_graph.summary:
            summary += f" — stack: {service_graph.summary}"

        # 7. Relevant git history (why/when this changed) — active repo only
        recent_history = self._collect_history(task_description, candidates)
        if recent_history and recent_history.summary:
            summary += f" — history: {recent_history.summary}"

        return ContextPack(
            task=task_description,
            primary_files=primary,
            supporting_files=supporting,
            summary=summary,
            service_graph=service_graph,
            recent_history=recent_history,
        )

    def _build_service_graph(self) -> Optional[ServiceGraph]:
        """Parse repo manifests into a coarse dependency graph. Never raises."""
        try:
            from app.modules.service_graph import build_service_graph
            raw = build_service_graph(str(self.repo_path))
            nodes = [ServiceNode(**nd) for nd in raw.get("nodes", [])]
            if not nodes:
                return None
            return ServiceGraph(nodes=nodes, summary=raw.get("summary", ""))
        except Exception as exc:
            logger.warning(f"Service graph unavailable for context pack: {exc}")
            return None

    def _collect_history(
        self, task_description: str, candidates: List[FileContext]
    ) -> Optional[GitHistory]:
        """Surface git commits relevant to the task. Never raises."""
        try:
            from app.modules.git_history import (
                find_relevant_commits, summarize_history,
            )
            paths = [c.path for c in candidates if not c.repo]
            commits = find_relevant_commits(str(self.repo_path), task_description, paths)
            if not commits:
                return None
            infos = [CommitInfo(**c) for c in commits]
            return GitHistory(commits=infos, summary=summarize_history(commits))
        except Exception as exc:
            logger.warning(f"Git history unavailable for context pack: {exc}")
            return None


    def _find_related_files_smart(
        self,
        current_file: str,
        file_content: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Find files related to current file using smart heuristics.

        Args:
            current_file: Current file path
            file_content: Content of current file (for import detection)

        Returns:
            List of related file info dicts
        """
        related = []

        try:
            current_path = Path(current_file)

            # 1. Extract imports from file content
            if file_content:
                imports = self._extract_imports(file_content, current_path.suffix)
                for imp in imports[:self.max_related_files]:
                    related.append({
                        "path": imp,
                        "reason": "imported"
                    })

            # 2. Find test files
            test_file = self._find_test_file(current_file)
            if test_file and len(related) < self.max_related_files:
                related.append({
                    "path": test_file,
                    "reason": "test_file"
                })

            # 3. Find files in same directory (if we need more)
            if len(related) < self.max_related_files:
                same_dir = self._find_files_in_same_directory(current_file)
                for f in same_dir[:self.max_related_files - len(related)]:
                    related.append({
                        "path": f,
                        "reason": "same_directory"
                    })

        except Exception as e:
            logger.warning(f"Failed to find related files: {e}")

        return related

    def find_related_files(
        self,
        current_file: Optional[str] = None,
        query: Optional[str] = None
    ) -> List[str]:
        """
        Find files related to current context (legacy method).

        Args:
            current_file: Current file path
            query: Search query

        Returns:
            List of related file paths
        """
        if current_file:
            smart_results = self._find_related_files_smart(current_file)
            return [r["path"] for r in smart_results]
        return []

    def get_file_context(self, file_path: str, line_range: Optional[tuple] = None) -> Optional[str]:
        """
        Get content of a specific file.

        Args:
            file_path: Relative path to file
            line_range: Optional (start_line, end_line) tuple

        Returns:
            File content or None
        """
        try:
            content = get_file_content(str(self.repo_path), file_path)

            if content and line_range:
                lines = content.splitlines()
                start, end = line_range
                content = '\n'.join(lines[start-1:end])

            return content
        except Exception as e:
            logger.error(f"Failed to get file context: {e}")
            return None

    def _extract_imports(self, content: str, file_ext: str) -> List[str]:
        """
        Extract import statements from file content.

        Args:
            content: File content
            file_ext: File extension (.py, .ts, .js, etc.)

        Returns:
            List of imported file paths (relative)
        """
        imports = []

        try:
            if file_ext in ['.py']:
                # Python imports: from X import Y, import X
                for match in re.finditer(r'from\s+([a-zA-Z0-9_.]+)\s+import', content):
                    module = match.group(1).replace('.', '/')
                    imports.append(f"{module}.py")
                for match in re.finditer(r'^import\s+([a-zA-Z0-9_.]+)', content, re.MULTILINE):
                    module = match.group(1).replace('.', '/')
                    imports.append(f"{module}.py")

            elif file_ext in ['.ts', '.tsx', '.js', '.jsx']:
                # TypeScript/JavaScript imports: import X from 'Y'
                for match in re.finditer(r'from\s+[\'"]([^\'\"]+)[\'"]', content):
                    path = match.group(1)
                    if path.startswith('.'):
                        imports.append(path)

        except Exception as e:
            logger.debug(f"Failed to extract imports: {e}")

        return imports[:10]  # Limit to 10

    def _find_test_file(self, file_path: str) -> Optional[str]:
        """
        Find corresponding test file for a source file.

        Args:
            file_path: Source file path

        Returns:
            Test file path or None
        """
        try:
            path = Path(file_path)
            stem = path.stem
            ext = path.suffix

            # Common test patterns
            test_patterns = [
                f"test_{stem}{ext}",
                f"{stem}_test{ext}",
                f"{stem}.test{ext}",
                f"{stem}.spec{ext}"
            ]

            # Check in same directory
            for pattern in test_patterns:
                test_path = path.parent / pattern
                if (self.repo_path / test_path).exists():
                    return str(test_path)

            # Check in tests directory
            for pattern in test_patterns:
                test_path = Path("tests") / pattern
                if (self.repo_path / test_path).exists():
                    return str(test_path)

        except Exception as e:
            logger.debug(f"Failed to find test file: {e}")

        return None

    def _find_files_in_same_directory(self, file_path: str) -> List[str]:
        """
        Find other files in the same directory.

        Args:
            file_path: Current file path

        Returns:
            List of file paths in same directory
        """
        try:
            path = Path(file_path)
            directory = self.repo_path / path.parent

            if directory.exists():
                files = []
                for f in directory.iterdir():
                    if f.is_file() and f.suffix == path.suffix and f.name != path.name:
                        rel_path = f.relative_to(self.repo_path)
                        files.append(str(rel_path))
                return files[:5]
        except Exception as e:
            logger.debug(f"Failed to find files in directory: {e}")

        return []

    def _truncate_content(self, content: str) -> str:
        """
        Truncate content if it exceeds max lines.

        Args:
            content: File content

        Returns:
            Truncated content
        """
        lines = content.splitlines()
        if len(lines) > self.max_context_lines:
            truncated = lines[:self.max_context_lines]
            truncated.append(f"\n... (truncated {len(lines) - self.max_context_lines} lines)")
            return '\n'.join(truncated)
        return content

    def build_prompt_context(self, context: Dict) -> str:
        """
        Build context string for LLM prompt.

        Args:
            context: Context dictionary

        Returns:
            Formatted context string
        """
        parts = []

        if context.get("repo_summary"):
            summary = context["repo_summary"]
            parts.append(f"Repository: {summary.get('total_files', 0)} files, {summary.get('total_lines', 0)} lines")
            if summary.get("languages"):
                parts.append(f"Languages: {', '.join(summary['languages'][:5])}")

        if context.get("current_file"):
            parts.append(f"Current file: {context['current_file']}")

        if context.get("selected_code"):
            parts.append(f"Selected code:\n```\n{context['selected_code']}\n```")
        elif context.get("current_file_content"):
            content = self._truncate_content(context["current_file_content"])
            parts.append(f"File content:\n```\n{content}\n```")

        if context.get("related_files"):
            related = context["related_files"][:3]
            if related:
                files_str = ", ".join([r.get("path", r) if isinstance(r, dict) else r for r in related])
                parts.append(f"Related files: {files_str}")

        return "\n\n".join(parts)


# Global context engine instance
_context_engine: Optional[ContextEngine] = None


def get_context_engine(repo_path: Optional[str] = None) -> ContextEngine:
    """Get global context engine instance."""
    global _context_engine
    if _context_engine is None:
        if repo_path is None:
            import os
            repo_path = os.getenv("REPO_PATH", ".")
        _context_engine = ContextEngine(repo_path)
    return _context_engine

