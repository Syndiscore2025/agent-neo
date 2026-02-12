"""
Tests for Repository Cloner Module
"""

import pytest
from unittest.mock import patch, MagicMock
import tempfile
import os
from pathlib import Path

from app.modules.repo_cloner import (
    CloneResult,
    CloneConfig,
    _get_repo_cache_path,
    _ensure_cache_dir,
    _is_directory_dirty,
    _sanitize_log_url,
    shallow_clone,
    cleanup_clone,
    cleanup_all_clones,
    get_cache_status
)


class TestCloneResult:
    """Tests for CloneResult dataclass."""
    
    def test_to_dict_success(self):
        result = CloneResult(
            success=True,
            repo_path="/path/to/repo",
            clone_time_seconds=1.5
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["repo_path"] == "/path/to/repo"
        assert d["clone_time_seconds"] == 1.5
    
    def test_to_dict_failure(self):
        result = CloneResult(
            success=False,
            repo_path=None,
            error="Clone failed"
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Clone failed"


class TestCloneConfig:
    """Tests for CloneConfig dataclass."""
    
    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = CloneConfig.from_env()
            assert config.cache_dir == "/opt/agent-neo/calibration"
            assert config.max_clone_time_seconds == 120
            assert config.cleanup_on_error is True
    
    def test_from_env_custom(self):
        env = {
            "CALIBRATION_CACHE_DIR": "/custom/cache",
            "CALIBRATION_CLONE_TIMEOUT": "60"
        }
        with patch.dict(os.environ, env, clear=True):
            config = CloneConfig.from_env()
            assert config.cache_dir == "/custom/cache"
            assert config.max_clone_time_seconds == 60


class TestCachePath:
    """Tests for cache path generation."""

    def test_get_repo_cache_path(self):
        path = _get_repo_cache_path("/cache", "owner/repo")
        path_str = str(path)
        assert "owner_repo" in path_str
        # Works on both Windows and Unix
        assert "cache" in path_str

    def test_cache_path_deterministic(self):
        path1 = _get_repo_cache_path("/cache", "owner/repo")
        path2 = _get_repo_cache_path("/cache", "owner/repo")
        assert path1 == path2


class TestSanitizeUrl:
    """Tests for URL sanitization."""
    
    def test_sanitize_url_with_token(self):
        url = "https://ghp_abc123@github.com/owner/repo.git"
        sanitized = _sanitize_log_url(url)
        assert "ghp_abc123" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_sanitize_url_without_token(self):
        url = "https://github.com/owner/repo.git"
        sanitized = _sanitize_log_url(url)
        assert sanitized == url
    
    def test_sanitize_url_with_user_pass(self):
        url = "https://user:password@github.com/owner/repo.git"
        sanitized = _sanitize_log_url(url)
        assert "password" not in sanitized


class TestEnsureCacheDir:
    """Tests for cache directory creation."""
    
    def test_ensure_cache_dir_creates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = os.path.join(tmpdir, "new_cache")
            error = _ensure_cache_dir(cache_dir)
            assert error is None
            assert os.path.exists(cache_dir)
    
    def test_ensure_cache_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            error = _ensure_cache_dir(tmpdir)
            assert error is None


class TestDirectoryDirty:
    """Tests for dirty directory detection."""
    
    def test_nonexistent_not_dirty(self):
        assert _is_directory_dirty(Path("/nonexistent/path")) is False


class TestCleanup:
    """Tests for cleanup functions."""
    
    def test_cleanup_nonexistent(self):
        result = cleanup_clone("/nonexistent/path")
        assert result is True
    
    def test_cleanup_clone_removes_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = os.path.join(tmpdir, "to_remove")
            os.makedirs(test_dir)
            assert os.path.exists(test_dir)
            
            cleanup_clone(test_dir)
            assert not os.path.exists(test_dir)


class TestCacheStatus:
    """Tests for cache status."""
    
    def test_cache_status_nonexistent(self):
        status = get_cache_status("/nonexistent/path")
        assert status["exists"] is False
        assert status["repo_count"] == 0
    
    def test_cache_status_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            status = get_cache_status(tmpdir)
            assert status["exists"] is True
            assert status["repo_count"] == 0

