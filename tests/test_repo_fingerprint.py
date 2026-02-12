"""
Tests for Repository Fingerprint Extraction Module
"""

import pytest
from unittest.mock import patch, MagicMock
import tempfile
import os
from pathlib import Path

from app.modules.repo_fingerprint import (
    RepoFingerprint,
    extract_fingerprint,
    _detect_frameworks,
    _detect_postgresql,
    _detect_migration_tool,
    _detect_health_endpoints,
    _detect_structured_logging,
    _detect_env_var_usage,
    _detect_ci
)


class TestRepoFingerprint:
    """Tests for RepoFingerprint dataclass."""
    
    def test_to_dict(self):
        fp = RepoFingerprint(
            repo_name="test",
            full_name="owner/test",
            primary_language="python",
            postgresql_detected=True
        )
        d = fp.to_dict()
        assert d["repo_name"] == "test"
        assert d["full_name"] == "owner/test"
        assert d["primary_language"] == "python"
        assert d["postgresql_detected"] is True


class TestFrameworkDetection:
    """Tests for framework detection."""
    
    def test_detect_fastapi(self):
        content = "from fastapi import FastAPI\napp = FastAPI()"
        frameworks = _detect_frameworks(content)
        assert "fastapi" in frameworks
    
    def test_detect_django(self):
        content = "from django.db import models\nINSTALLED_APPS = []"
        frameworks = _detect_frameworks(content)
        assert "django" in frameworks
    
    def test_detect_flask(self):
        content = "from flask import Flask\napp = Flask(__name__)"
        frameworks = _detect_frameworks(content)
        assert "flask" in frameworks
    
    def test_detect_react(self):
        content = "import React from 'react'"
        frameworks = _detect_frameworks(content)
        assert "react" in frameworks
    
    def test_detect_express(self):
        content = "const express = require('express')"
        frameworks = _detect_frameworks(content)
        assert "express" in frameworks
    
    def test_no_framework(self):
        content = "print('hello world')"
        frameworks = _detect_frameworks(content)
        assert frameworks == []


class TestPostgreSQLDetection:
    """Tests for PostgreSQL detection."""
    
    def test_detect_psycopg2(self):
        content = "import psycopg2\nconn = psycopg2.connect()"
        detected, patterns = _detect_postgresql(content)
        assert detected is True
        assert len(patterns) > 0
    
    def test_detect_asyncpg(self):
        content = "import asyncpg\nconn = await asyncpg.connect()"
        detected, patterns = _detect_postgresql(content)
        assert detected is True
    
    def test_detect_postgresql_url(self):
        content = "DATABASE_URL=postgresql://localhost/db"
        detected, patterns = _detect_postgresql(content)
        assert detected is True
    
    def test_no_postgresql(self):
        content = "import sqlite3\nconn = sqlite3.connect(':memory:')"
        detected, patterns = _detect_postgresql(content)
        assert detected is False
        assert patterns == []


class TestMigrationToolDetection:
    """Tests for migration tool detection."""
    
    def test_detect_alembic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            alembic_dir = os.path.join(tmpdir, "alembic")
            os.makedirs(alembic_dir)
            result = _detect_migration_tool(Path(tmpdir))
            assert result == "alembic"
    
    def test_detect_prisma(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prisma_dir = os.path.join(tmpdir, "prisma")
            os.makedirs(prisma_dir)
            result = _detect_migration_tool(Path(tmpdir))
            assert result == "prisma"
    
    def test_no_migration_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _detect_migration_tool(Path(tmpdir))
            assert result is None


class TestHealthEndpointDetection:
    """Tests for health endpoint detection."""
    
    def test_detect_health(self):
        content = "@app.get('/health')"
        assert _detect_health_endpoints(content) is True
    
    def test_detect_healthz(self):
        content = "router.get('/healthz')"
        assert _detect_health_endpoints(content) is True
    
    def test_detect_readiness(self):
        content = "app.get('/health/ready')"
        assert _detect_health_endpoints(content) is True
    
    def test_no_health_endpoint(self):
        content = "app.get('/api/users')"
        assert _detect_health_endpoints(content) is False


class TestLoggingDetection:
    """Tests for structured logging detection."""
    
    def test_detect_structlog(self):
        content = "import structlog\nlogger = structlog.get_logger()"
        assert _detect_structured_logging(content) is True
    
    def test_detect_python_logging(self):
        content = "import logging\nlogger = logging.getLogger(__name__)"
        assert _detect_structured_logging(content) is True
    
    def test_no_logging(self):
        content = "print('debug message')"
        assert _detect_structured_logging(content) is False

