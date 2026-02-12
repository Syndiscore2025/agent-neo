"""
AGENT NEO - GitHub Discovery Module

Discovers and filters repositories from GitHub accounts/organizations
for enterprise calibration.

SECURITY:
- Never log GITHUB_TOKEN
- Never persist raw repo source
- Never log clone URLs with embedded tokens
- All operations are read-only
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set
from urllib.parse import urljoin
import json

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# Security: Use a filtered logger that never logs tokens
class SecureLogger:
    """Logger wrapper that filters sensitive data."""

    SENSITIVE_PATTERNS = ["ghp_", "gho_", "github_pat_", "token", "password", "secret"]

    def __init__(self, logger):
        self._logger = logger

    def _filter_message(self, msg: str) -> str:
        """Remove any sensitive data from log messages."""
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern.lower() in msg.lower():
                # Redact the line after sensitive pattern
                import re
                msg = re.sub(
                    rf"{pattern}[^\s]*",
                    f"{pattern}[REDACTED]",
                    msg,
                    flags=re.IGNORECASE
                )
        return msg

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(self._filter_message(msg), *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(self._filter_message(msg), *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(self._filter_message(msg), *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(self._filter_message(msg), *args, **kwargs)


logger = SecureLogger(logging.getLogger(__name__))


@dataclass
class DiscoveredRepo:
    """Represents a discovered GitHub repository."""
    repo_name: str
    full_name: str
    clone_url: str
    default_branch: str
    topics: List[str]
    private: bool
    language: Optional[str] = None
    size_kb: int = 0
    stars: int = 0
    
    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "full_name": self.full_name,
            "clone_url": self.clone_url,
            "default_branch": self.default_branch,
            "topics": self.topics,
            "private": self.private,
            "language": self.language,
            "size_kb": self.size_kb,
            "stars": self.stars
        }


@dataclass
class DiscoveryResult:
    """Result of GitHub repository discovery."""
    repos: List[DiscoveredRepo]
    total_found: int
    total_filtered: int
    filters_applied: List[str]
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "repos": [r.to_dict() for r in self.repos],
            "total_found": self.total_found,
            "total_filtered": self.total_filtered,
            "filters_applied": self.filters_applied,
            "errors": self.errors
        }


def get_github_config() -> dict:
    """Get GitHub configuration from environment."""
    return {
        "token": os.getenv("GITHUB_TOKEN"),
        "owner": os.getenv("GITHUB_OWNER"),
        "type": os.getenv("GITHUB_TYPE", "personal"),
        "include_topics": _parse_topics(os.getenv("CALIBRATION_INCLUDE_TOPICS", "")),
        "exclude_topics": _parse_topics(os.getenv("CALIBRATION_EXCLUDE_TOPICS", "prototype,experimental,sandbox")),
        "max_repos": int(os.getenv("CALIBRATION_MAX_REPOS", "50")),
        "cache_dir": os.getenv("CALIBRATION_CACHE_DIR", "/opt/agent-neo/calibration")
    }


def _parse_topics(topics_str: str) -> Set[str]:
    """Parse comma-separated topics into a set."""
    if not topics_str:
        return set()
    return {t.strip().lower() for t in topics_str.split(",") if t.strip()}


def validate_github_config(config: dict) -> List[str]:
    """Validate GitHub configuration. Returns list of errors."""
    errors = []
    
    if not config.get("token"):
        errors.append("GITHUB_TOKEN is required for repository discovery")
    
    if not config.get("owner"):
        errors.append("GITHUB_OWNER is required for repository discovery")
    
    if config.get("type") not in ("personal", "org"):
        errors.append("GITHUB_TYPE must be 'personal' or 'org'")
    
    if config.get("max_repos", 0) < 1 or config.get("max_repos", 0) > 100:
        errors.append("CALIBRATION_MAX_REPOS must be between 1 and 100")
    
    return errors


def _get_api_url(config: dict) -> str:
    """Get the appropriate GitHub API URL based on account type."""
    owner = config["owner"]
    if config["type"] == "org":
        return f"https://api.github.com/orgs/{owner}/repos"
    else:
        return "https://api.github.com/user/repos"


def _get_headers(token: str) -> dict:
    """Get headers for GitHub API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def _should_include_repo(
    repo: dict,
    include_topics: Set[str],
    exclude_topics: Set[str]
) -> bool:
    """Determine if a repo should be included based on filters."""
    # Exclude archived repos
    if repo.get("archived", False):
        return False
    
    # Exclude forks
    if repo.get("fork", False):
        return False
    
    # Get repo topics (lowercase)
    repo_topics = {t.lower() for t in repo.get("topics", [])}
    
    # Check exclude topics
    if exclude_topics and repo_topics & exclude_topics:
        return False
    
    # Check include topics (if specified, repo must have at least one)
    if include_topics and not (repo_topics & include_topics):
        return False

    return True


def discover_repositories(config: Optional[dict] = None) -> DiscoveryResult:
    """
    Discover repositories from GitHub account/organization.

    Args:
        config: Optional config dict. If None, reads from environment.

    Returns:
        DiscoveryResult with filtered repositories
    """
    if not HTTPX_AVAILABLE:
        return DiscoveryResult(
            repos=[],
            total_found=0,
            total_filtered=0,
            filters_applied=[],
            errors=["httpx library not available. Install with: pip install httpx"]
        )

    if config is None:
        config = get_github_config()

    # Validate config
    validation_errors = validate_github_config(config)
    if validation_errors:
        return DiscoveryResult(
            repos=[],
            total_found=0,
            total_filtered=0,
            filters_applied=[],
            errors=validation_errors
        )

    api_url = _get_api_url(config)
    headers = _get_headers(config["token"])

    all_repos = []
    errors = []
    page = 1
    per_page = 100

    try:
        with httpx.Client(timeout=30.0) as client:
            while True:
                params = {"page": page, "per_page": per_page}

                # For personal repos, filter by owner
                if config["type"] == "personal":
                    params["affiliation"] = "owner"

                response = client.get(api_url, headers=headers, params=params)

                if response.status_code == 401:
                    errors.append("GitHub token is invalid or expired")
                    break
                elif response.status_code == 403:
                    errors.append("GitHub API rate limit exceeded or insufficient permissions")
                    break
                elif response.status_code != 200:
                    errors.append(f"GitHub API error: {response.status_code}")
                    break

                repos = response.json()
                if not repos:
                    break

                all_repos.extend(repos)

                # Check if we've hit the max
                if len(all_repos) >= config["max_repos"] * 2:
                    break

                page += 1

    except httpx.TimeoutException:
        errors.append("GitHub API request timed out")
    except Exception as e:
        errors.append(f"GitHub API error: {str(e)}")
        logger.error(f"GitHub discovery error: {e}")

    # Filter repos
    filters_applied = []
    filters_applied.append("exclude_archived")
    filters_applied.append("exclude_forks")

    if config["exclude_topics"]:
        filters_applied.append(f"exclude_topics:{','.join(config['exclude_topics'])}")

    if config["include_topics"]:
        filters_applied.append(f"include_topics:{','.join(config['include_topics'])}")

    filtered_repos = []
    for repo in all_repos:
        if _should_include_repo(repo, config["include_topics"], config["exclude_topics"]):
            filtered_repos.append(DiscoveredRepo(
                repo_name=repo["name"],
                full_name=repo["full_name"],
                clone_url=repo["clone_url"],
                default_branch=repo.get("default_branch", "main"),
                topics=repo.get("topics", []),
                private=repo.get("private", False),
                language=repo.get("language"),
                size_kb=repo.get("size", 0),
                stars=repo.get("stargazers_count", 0)
            ))

    # Apply max repos limit
    total_filtered = len(filtered_repos)
    filtered_repos = filtered_repos[:config["max_repos"]]
    filters_applied.append(f"max_repos:{config['max_repos']}")

    logger.info(f"Discovered {len(all_repos)} repos, filtered to {len(filtered_repos)}")

    return DiscoveryResult(
        repos=filtered_repos,
        total_found=len(all_repos),
        total_filtered=total_filtered,
        filters_applied=filters_applied,
        errors=errors
    )

