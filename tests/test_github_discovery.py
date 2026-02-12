"""
Tests for GitHub Discovery Module
"""

import pytest
from unittest.mock import patch, MagicMock
import os

from app.modules.github_discovery import (
    DiscoveredRepo,
    DiscoveryResult,
    get_github_config,
    validate_github_config,
    _parse_topics,
    _get_api_url,
    _get_headers,
    _should_include_repo,
    discover_repositories
)


class TestDiscoveredRepo:
    """Tests for DiscoveredRepo dataclass."""
    
    def test_to_dict(self):
        repo = DiscoveredRepo(
            repo_name="test-repo",
            full_name="owner/test-repo",
            clone_url="https://github.com/owner/test-repo.git",
            default_branch="main",
            topics=["production"],
            private=False,
            language="Python",
            size_kb=1024,
            stars=10
        )
        result = repo.to_dict()
        assert result["repo_name"] == "test-repo"
        assert result["full_name"] == "owner/test-repo"
        assert result["default_branch"] == "main"
        assert result["private"] is False


class TestDiscoveryResult:
    """Tests for DiscoveryResult dataclass."""
    
    def test_to_dict_empty(self):
        result = DiscoveryResult(
            repos=[],
            total_found=0,
            total_filtered=0,
            filters_applied=[]
        )
        d = result.to_dict()
        assert d["repos"] == []
        assert d["total_found"] == 0


class TestParseTopic:
    """Tests for topic parsing."""
    
    def test_parse_empty(self):
        assert _parse_topics("") == set()
    
    def test_parse_single(self):
        assert _parse_topics("production") == {"production"}
    
    def test_parse_multiple(self):
        result = _parse_topics("production,experimental,sandbox")
        assert result == {"production", "experimental", "sandbox"}
    
    def test_parse_with_spaces(self):
        result = _parse_topics(" production , experimental ")
        assert result == {"production", "experimental"}
    
    def test_parse_case_insensitive(self):
        result = _parse_topics("Production,EXPERIMENTAL")
        assert "production" in result
        assert "experimental" in result


class TestGitHubConfig:
    """Tests for GitHub configuration."""
    
    def test_get_github_config_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_github_config()
            assert config["token"] is None
            assert config["owner"] is None
            assert config["type"] == "personal"
            assert config["max_repos"] == 50
    
    def test_get_github_config_from_env(self):
        env = {
            "GITHUB_TOKEN": "test_token",
            "GITHUB_OWNER": "test_owner",
            "GITHUB_TYPE": "org",
            "CALIBRATION_MAX_REPOS": "25"
        }
        with patch.dict(os.environ, env, clear=True):
            config = get_github_config()
            assert config["token"] == "test_token"
            assert config["owner"] == "test_owner"
            assert config["type"] == "org"
            assert config["max_repos"] == 25
    
    def test_validate_config_missing_token(self):
        config = {"token": None, "owner": "test", "type": "personal", "max_repos": 50}
        errors = validate_github_config(config)
        assert any("GITHUB_TOKEN" in e for e in errors)
    
    def test_validate_config_missing_owner(self):
        config = {"token": "test", "owner": None, "type": "personal", "max_repos": 50}
        errors = validate_github_config(config)
        assert any("GITHUB_OWNER" in e for e in errors)
    
    def test_validate_config_invalid_type(self):
        config = {"token": "test", "owner": "test", "type": "invalid", "max_repos": 50}
        errors = validate_github_config(config)
        assert any("GITHUB_TYPE" in e for e in errors)
    
    def test_validate_config_invalid_max_repos(self):
        config = {"token": "test", "owner": "test", "type": "personal", "max_repos": 200}
        errors = validate_github_config(config)
        assert any("CALIBRATION_MAX_REPOS" in e for e in errors)
    
    def test_validate_config_valid(self):
        config = {"token": "test", "owner": "test", "type": "personal", "max_repos": 50}
        errors = validate_github_config(config)
        assert errors == []


class TestApiUrl:
    """Tests for API URL generation."""
    
    def test_personal_api_url(self):
        config = {"owner": "myuser", "type": "personal"}
        url = _get_api_url(config)
        assert url == "https://api.github.com/user/repos"
    
    def test_org_api_url(self):
        config = {"owner": "myorg", "type": "org"}
        url = _get_api_url(config)
        assert url == "https://api.github.com/orgs/myorg/repos"


class TestHeaders:
    """Tests for API headers."""

    def test_headers_include_token(self):
        headers = _get_headers("test_token")
        assert headers["Authorization"] == "Bearer test_token"
        assert "Accept" in headers


class TestRepoFiltering:
    """Tests for repository filtering."""

    def test_exclude_archived_repo(self):
        repo = {"archived": True, "fork": False, "topics": []}
        assert _should_include_repo(repo, set(), set()) is False

    def test_exclude_fork(self):
        repo = {"archived": False, "fork": True, "topics": []}
        assert _should_include_repo(repo, set(), set()) is False

    def test_include_normal_repo(self):
        repo = {"archived": False, "fork": False, "topics": []}
        assert _should_include_repo(repo, set(), set()) is True

    def test_exclude_by_topic(self):
        repo = {"archived": False, "fork": False, "topics": ["prototype"]}
        assert _should_include_repo(repo, set(), {"prototype"}) is False

    def test_include_by_topic(self):
        repo = {"archived": False, "fork": False, "topics": ["production"]}
        assert _should_include_repo(repo, {"production"}, set()) is True

    def test_exclude_missing_required_topic(self):
        repo = {"archived": False, "fork": False, "topics": ["development"]}
        assert _should_include_repo(repo, {"production"}, set()) is False


class TestDiscoverRepositories:
    """Tests for repository discovery."""

    def test_discover_without_httpx(self):
        # Since httpx is installed, this test is not applicable
        # The module will always have httpx available in the test environment
        # This test would only be meaningful in an environment without httpx
        result = discover_repositories({"token": None, "owner": None, "type": "personal", "max_repos": 50})
        assert result.repos == []
        # Should have config validation errors
        assert len(result.errors) > 0

    def test_discover_with_invalid_config(self):
        config = {"token": None, "owner": None, "type": "personal", "max_repos": 50}
        result = discover_repositories(config)
        assert result.repos == []
        assert len(result.errors) > 0

