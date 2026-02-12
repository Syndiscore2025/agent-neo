"""
AGENT NEO - Repository Fingerprint Extraction Module

Extracts deterministic architectural fingerprints from cloned repositories.
Outputs structured JSON only - never sends raw source to reasoning layer.
"""

import os
import re
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from collections import Counter
import json

logger = logging.getLogger(__name__)


# Language detection by file extension
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".swift": "swift",
    ".kt": "kotlin"
}

# Framework detection patterns
FRAMEWORK_PATTERNS = {
    "fastapi": [r"from\s+fastapi\s+import", r"FastAPI\s*\("],
    "django": [r"from\s+django", r"INSTALLED_APPS"],
    "flask": [r"from\s+flask\s+import", r"Flask\s*\("],
    "express": [r"require\(['\"]express['\"]\)", r"from\s+['\"]express['\"]"],
    "react": [r"from\s+['\"]react['\"]", r"import\s+React"],
    "nextjs": [r"from\s+['\"]next", r"next\.config"],
    "spring": [r"@SpringBootApplication", r"springframework"],
    "rails": [r"Rails\.application", r"ActiveRecord"],
    "gin": [r"github\.com/gin-gonic/gin"],
    "actix": [r"actix_web", r"actix-web"]
}

# PostgreSQL usage patterns
POSTGRES_PATTERNS = [
    r"psycopg2",
    r"asyncpg",
    r"postgresql://",
    r"postgres://",
    r"DATABASE_URL.*postgres",
    r"pg_connect",
    r"PG::",
    r"postgres\.createPool",
    r"from\s+sqlalchemy.*postgresql"
]

# Health endpoint patterns
HEALTH_PATTERNS = [
    r"/health",
    r"/healthz",
    r"/health/live",
    r"/health/ready",
    r"/readiness",
    r"/liveness",
    r"healthcheck"
]

# Structured logging patterns
LOGGING_PATTERNS = [
    r"structlog",
    r"logging\.getLogger",
    r"winston",
    r"bunyan",
    r"pino",
    r"zap\.Logger",
    r"logrus",
    r"slog"
]


@dataclass
class RepoFingerprint:
    """Structural fingerprint of a repository."""
    repo_name: str
    full_name: str
    
    # Language & Framework
    primary_language: Optional[str] = None
    language_distribution: Dict[str, float] = field(default_factory=dict)
    frameworks_detected: List[str] = field(default_factory=list)
    
    # Structure
    module_depth_avg: float = 0.0
    total_files: int = 0
    total_lines: int = 0
    file_size_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Enterprise patterns
    postgresql_detected: bool = False
    postgresql_patterns: List[str] = field(default_factory=list)
    migration_tool: Optional[str] = None
    health_endpoints_detected: bool = False
    structured_logging_detected: bool = False
    env_var_usage: bool = False
    
    # Testing
    test_folder_present: bool = False
    test_file_count: int = 0
    test_to_code_ratio: float = 0.0
    
    # Infrastructure
    docker_present: bool = False
    ci_present: bool = False
    ci_tool: Optional[str] = None
    
    # Async patterns
    async_usage_count: int = 0
    async_ratio: float = 0.0
    
    # Git metrics (last 50 commits)
    commit_count: int = 0
    commit_frequency_per_week: float = 0.0
    unique_authors: int = 0
    
    # Coupling
    import_count: int = 0
    coupling_density: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "full_name": self.full_name,
            "primary_language": self.primary_language,
            "language_distribution": self.language_distribution,
            "frameworks_detected": self.frameworks_detected,
            "module_depth_avg": self.module_depth_avg,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "file_size_distribution": self.file_size_distribution,
            "postgresql_detected": self.postgresql_detected,
            "postgresql_patterns": self.postgresql_patterns,
            "migration_tool": self.migration_tool,
            "health_endpoints_detected": self.health_endpoints_detected,
            "structured_logging_detected": self.structured_logging_detected,
            "env_var_usage": self.env_var_usage,
            "test_folder_present": self.test_folder_present,
            "test_file_count": self.test_file_count,
            "test_to_code_ratio": self.test_to_code_ratio,
            "docker_present": self.docker_present,
            "ci_present": self.ci_present,
            "ci_tool": self.ci_tool,
            "async_usage_count": self.async_usage_count,
            "async_ratio": self.async_ratio,
            "commit_count": self.commit_count,
            "commit_frequency_per_week": self.commit_frequency_per_week,
            "unique_authors": self.unique_authors,
            "import_count": self.import_count,
            "coupling_density": self.coupling_density
        }


def extract_fingerprint(repo_path: str, full_name: str) -> RepoFingerprint:
    """
    Extract structural fingerprint from a cloned repository.

    Args:
        repo_path: Path to cloned repository
        full_name: Full repository name (owner/repo)

    Returns:
        RepoFingerprint with extracted metrics
    """
    path = Path(repo_path)
    repo_name = full_name.split("/")[-1] if "/" in full_name else full_name

    fingerprint = RepoFingerprint(
        repo_name=repo_name,
        full_name=full_name
    )

    # Collect all code files
    code_files = []
    test_files = []
    all_content = []
    language_lines = Counter()
    depths = []
    file_sizes = {"small": 0, "medium": 0, "large": 0}  # <100, 100-500, >500 lines

    for root, dirs, files in os.walk(path):
        # Skip hidden and vendor directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                   ("node_modules", "vendor", "venv", ".venv", "__pycache__", "dist", "build")]

        rel_root = Path(root).relative_to(path)
        depth = len(rel_root.parts)

        for file in files:
            file_path = Path(root) / file
            ext = file_path.suffix.lower()

            if ext in LANGUAGE_EXTENSIONS:
                try:
                    content = file_path.read_text(errors="ignore")
                    lines = len(content.splitlines())

                    language_lines[LANGUAGE_EXTENSIONS[ext]] += lines
                    code_files.append(file_path)
                    all_content.append(content)
                    depths.append(depth)

                    # File size distribution
                    if lines < 100:
                        file_sizes["small"] += 1
                    elif lines < 500:
                        file_sizes["medium"] += 1
                    else:
                        file_sizes["large"] += 1

                    # Check if test file
                    if "test" in file.lower() or "/tests/" in str(file_path).lower():
                        test_files.append(file_path)

                except Exception:
                    pass

    # Language distribution
    total_lines = sum(language_lines.values())
    if total_lines > 0:
        fingerprint.language_distribution = {
            lang: round(count / total_lines, 3)
            for lang, count in language_lines.most_common(5)
        }
        fingerprint.primary_language = language_lines.most_common(1)[0][0] if language_lines else None

    fingerprint.total_files = len(code_files)
    fingerprint.total_lines = total_lines
    fingerprint.file_size_distribution = file_sizes
    fingerprint.module_depth_avg = round(sum(depths) / len(depths), 2) if depths else 0

    # Combine content for pattern matching
    combined_content = "\n".join(all_content[:100])  # Limit to first 100 files

    # Framework detection
    fingerprint.frameworks_detected = _detect_frameworks(combined_content)

    # PostgreSQL detection
    fingerprint.postgresql_detected, fingerprint.postgresql_patterns = _detect_postgresql(combined_content)

    # Migration tool detection
    fingerprint.migration_tool = _detect_migration_tool(path)

    # Health endpoint detection
    fingerprint.health_endpoints_detected = _detect_health_endpoints(combined_content)

    # Structured logging detection
    fingerprint.structured_logging_detected = _detect_structured_logging(combined_content)

    # Env var usage
    fingerprint.env_var_usage = _detect_env_var_usage(path, combined_content)

    # Test metrics
    fingerprint.test_folder_present = (path / "tests").exists() or (path / "test").exists()
    fingerprint.test_file_count = len(test_files)
    code_file_count = len(code_files) - len(test_files)
    fingerprint.test_to_code_ratio = round(len(test_files) / code_file_count, 2) if code_file_count > 0 else 0

    # Infrastructure
    fingerprint.docker_present = (path / "Dockerfile").exists() or (path / "docker-compose.yml").exists()
    fingerprint.ci_present, fingerprint.ci_tool = _detect_ci(path)

    # Async patterns
    fingerprint.async_usage_count = len(re.findall(r"\basync\s+def\b|\basync\s+function\b|\bawait\b", combined_content))
    fingerprint.async_ratio = round(fingerprint.async_usage_count / max(total_lines, 1) * 100, 2)

    # Git metrics
    fingerprint.commit_count, fingerprint.commit_frequency_per_week, fingerprint.unique_authors = _get_git_metrics(path)

    # Import/coupling analysis
    fingerprint.import_count = len(re.findall(r"^import\s+|^from\s+\S+\s+import|require\(|^use\s+", combined_content, re.MULTILINE))
    fingerprint.coupling_density = round(fingerprint.import_count / max(len(code_files), 1), 2)

    return fingerprint


def _detect_frameworks(content: str) -> List[str]:
    """Detect frameworks from code content."""
    detected = []
    for framework, patterns in FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                detected.append(framework)
                break
    return detected


def _detect_postgresql(content: str) -> tuple:
    """Detect PostgreSQL usage and patterns."""
    found_patterns = []
    for pattern in POSTGRES_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            found_patterns.append(pattern)
    return bool(found_patterns), found_patterns[:5]  # Limit to 5


def _detect_migration_tool(path: Path) -> Optional[str]:
    """Detect migration tool in use."""
    if (path / "alembic").exists() or (path / "alembic.ini").exists():
        return "alembic"
    if (path / "migrations").exists():
        # Check for Django migrations
        if any((path / "migrations").glob("*.py")):
            return "django"
        return "generic"
    if (path / "db" / "migrate").exists():
        return "rails"
    if (path / "prisma").exists():
        return "prisma"
    if any(path.glob("**/flyway*")):
        return "flyway"
    return None


def _detect_health_endpoints(content: str) -> bool:
    """Detect health endpoint patterns."""
    for pattern in HEALTH_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def _detect_structured_logging(content: str) -> bool:
    """Detect structured logging usage."""
    for pattern in LOGGING_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def _detect_env_var_usage(path: Path, content: str) -> bool:
    """Detect environment variable usage."""
    if (path / ".env.example").exists() or (path / ".env.sample").exists():
        return True
    if re.search(r"os\.getenv|process\.env|ENV\[|std::env", content):
        return True
    return False


def _detect_ci(path: Path) -> tuple:
    """Detect CI/CD configuration."""
    if (path / ".github" / "workflows").exists():
        return True, "github_actions"
    if (path / ".gitlab-ci.yml").exists():
        return True, "gitlab"
    if (path / "Jenkinsfile").exists():
        return True, "jenkins"
    if (path / ".circleci").exists():
        return True, "circleci"
    if (path / ".travis.yml").exists():
        return True, "travis"
    if (path / "azure-pipelines.yml").exists():
        return True, "azure"
    return False, None


def _get_git_metrics(path: Path) -> tuple:
    """Get git commit metrics (last 50 commits)."""
    try:
        # Get last 50 commits
        result = subprocess.run(
            ["git", "log", "--oneline", "-50", "--format=%H|%ae|%ct"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return 0, 0.0, 0

        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0]:
            return 0, 0.0, 0

        commit_count = len(lines)
        authors = set()
        timestamps = []

        for line in lines:
            parts = line.split("|")
            if len(parts) >= 3:
                authors.add(parts[1])
                try:
                    timestamps.append(int(parts[2]))
                except ValueError:
                    pass

        # Calculate frequency
        if len(timestamps) >= 2:
            time_span_weeks = (max(timestamps) - min(timestamps)) / (7 * 24 * 3600)
            frequency = round(commit_count / max(time_span_weeks, 1), 2)
        else:
            frequency = 0.0

        return commit_count, frequency, len(authors)

    except Exception as e:
        logger.debug(f"Git metrics error: {e}")
        return 0, 0.0, 0

