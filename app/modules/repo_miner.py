"""
AGENT NEO - Repository Miner
Extracts structured patterns from Git repositories for calibration.
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class RepoFingerprint:
    """Structured fingerprint of a repository."""
    repo_name: str
    folder_structure: Dict[str, int]  # folder -> file count
    frameworks: List[str]
    database_patterns: List[str]
    env_var_patterns: List[str]
    logging_patterns: List[str]
    test_structure: Dict[str, Any]
    migration_usage: Optional[str]
    commit_message_style: Dict[str, Any]
    docker_usage: bool
    health_check_patterns: List[str]
    total_files: int
    total_lines: int


def clone_repo_shallow(repo_url: str, target_dir: Path) -> bool:
    """
    Clone repository shallow (depth=1) for analysis.
    
    Args:
        repo_url: Git repository URL
        target_dir: Target directory for clone
        
    Returns:
        True if successful, False otherwise
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        
        result = subprocess.run(
            ['git', 'clone', '--depth', '1', repo_url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to clone {repo_url}: {result.stderr}")
            return False
            
        logger.info(f"Successfully cloned {repo_url} to {target_dir}")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"Clone timeout for {repo_url}")
        return False
    except Exception as e:
        logger.error(f"Clone error for {repo_url}: {e}")
        return False


def extract_folder_structure(repo_path: Path) -> Dict[str, int]:
    """Extract folder structure with file counts."""
    structure = {}
    
    for root, dirs, files in os.walk(repo_path):
        # Skip .git directory
        if '.git' in root:
            continue
            
        rel_path = os.path.relpath(root, repo_path)
        if rel_path == '.':
            rel_path = 'root'
            
        structure[rel_path] = len(files)
        
    return structure


def detect_frameworks(repo_path: Path) -> List[str]:
    """Detect frameworks used in repository."""
    frameworks = []
    
    # Check for common framework indicators
    indicators = {
        'fastapi': ['from fastapi', 'import fastapi'],
        'flask': ['from flask', 'import flask'],
        'django': ['django.', 'DJANGO_SETTINGS'],
        'react': ['react', 'package.json'],
        'next.js': ['next.config', 'pages/'],
        'express': ['express()', 'require("express")'],
        'pytest': ['pytest', 'conftest.py'],
        'alembic': ['alembic', 'versions/'],
    }
    
    for framework, patterns in indicators.items():
        for pattern in patterns:
            # Search in common files
            if _search_in_repo(repo_path, pattern):
                frameworks.append(framework)
                break
                
    return list(set(frameworks))


def _search_in_repo(repo_path: Path, pattern: str) -> bool:
    """Search for pattern in repository files."""
    try:
        result = subprocess.run(
            ['git', 'grep', '-l', pattern],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except:
        return False


def detect_database_patterns(repo_path: Path) -> List[str]:
    """Detect database usage patterns."""
    patterns = []
    
    db_indicators = {
        'postgresql': ['psycopg2', 'asyncpg', 'postgresql://'],
        'sqlalchemy': ['from sqlalchemy', 'SQLAlchemy'],
        'alembic': ['alembic', 'env.py'],
        'connection_pooling': ['pool_size', 'max_overflow', 'QueuePool'],
    }
    
    for pattern_name, indicators in db_indicators.items():
        for indicator in indicators:
            if _search_in_repo(repo_path, indicator):
                patterns.append(pattern_name)
                break
                
    return list(set(patterns))


def detect_env_patterns(repo_path: Path) -> List[str]:
    """Detect environment variable patterns."""
    patterns = []

    if (repo_path / '.env.example').exists() or (repo_path / '.env.template').exists():
        patterns.append('env_template_exists')

    if _search_in_repo(repo_path, 'os.getenv') or _search_in_repo(repo_path, 'os.environ'):
        patterns.append('python_env_vars')

    if _search_in_repo(repo_path, 'python-dotenv'):
        patterns.append('dotenv_usage')

    return patterns


def detect_logging_patterns(repo_path: Path) -> List[str]:
    """Detect logging patterns."""
    patterns = []

    if _search_in_repo(repo_path, 'logging.basicConfig'):
        patterns.append('python_logging')

    if _search_in_repo(repo_path, 'json.dumps') and _search_in_repo(repo_path, 'logger'):
        patterns.append('structured_logging')

    return patterns


def detect_test_structure(repo_path: Path) -> Dict[str, Any]:
    """Detect test structure and patterns."""
    structure = {
        'has_tests': False,
        'test_framework': None,
        'test_directory': None,
        'test_count': 0
    }

    # Check for test directories
    test_dirs = ['tests', 'test', '__tests__']
    for test_dir in test_dirs:
        if (repo_path / test_dir).exists():
            structure['has_tests'] = True
            structure['test_directory'] = test_dir
            # Count test files
            test_files = list((repo_path / test_dir).rglob('test_*.py'))
            structure['test_count'] = len(test_files)
            break

    # Detect framework
    if (repo_path / 'pytest.ini').exists() or _search_in_repo(repo_path, 'import pytest'):
        structure['test_framework'] = 'pytest'
    elif _search_in_repo(repo_path, 'import unittest'):
        structure['test_framework'] = 'unittest'

    return structure


def detect_health_checks(repo_path: Path) -> List[str]:
    """Detect health check endpoints."""
    patterns = []

    if _search_in_repo(repo_path, '/health'):
        patterns.append('health_endpoint')
    if _search_in_repo(repo_path, '/health/live'):
        patterns.append('liveness_probe')
    if _search_in_repo(repo_path, '/health/ready'):
        patterns.append('readiness_probe')

    return patterns


def mine_repository(repo_path: Path, repo_name: str) -> RepoFingerprint:
    """
    Mine repository for patterns and structure.

    Args:
        repo_path: Path to repository
        repo_name: Name of repository

    Returns:
        RepoFingerprint object
    """
    logger.info(f"Mining repository: {repo_name}")

    # Extract patterns
    folder_structure = extract_folder_structure(repo_path)
    frameworks = detect_frameworks(repo_path)
    database_patterns = detect_database_patterns(repo_path)
    env_var_patterns = detect_env_patterns(repo_path)
    logging_patterns = detect_logging_patterns(repo_path)
    test_structure = detect_test_structure(repo_path)
    health_check_patterns = detect_health_checks(repo_path)

    # Check for Docker
    docker_usage = (repo_path / 'Dockerfile').exists() or (repo_path / 'docker-compose.yml').exists()

    # Check for migrations
    migration_usage = None
    if (repo_path / 'alembic').exists():
        migration_usage = 'alembic'
    elif (repo_path / 'migrations').exists():
        migration_usage = 'generic'

    # Count total files and lines
    total_files = 0
    total_lines = 0
    for root, dirs, files in os.walk(repo_path):
        if '.git' in root:
            continue
        total_files += len(files)
        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.go', '.rs')):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                        total_lines += len(f.readlines())
                except:
                    pass

    # Analyze commit messages (last 10)
    commit_style = analyze_commit_style(repo_path)

    return RepoFingerprint(
        repo_name=repo_name,
        folder_structure=folder_structure,
        frameworks=frameworks,
        database_patterns=database_patterns,
        env_var_patterns=env_var_patterns,
        logging_patterns=logging_patterns,
        test_structure=test_structure,
        migration_usage=migration_usage,
        commit_message_style=commit_style,
        docker_usage=docker_usage,
        health_check_patterns=health_check_patterns,
        total_files=total_files,
        total_lines=total_lines
    )


def analyze_commit_style(repo_path: Path) -> Dict[str, Any]:
    """Analyze commit message style from recent commits."""
    try:
        result = subprocess.run(
            ['git', 'log', '--format=%s', '-n', '10'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return {'analyzed': False}

        messages = result.stdout.strip().split('\n')

        # Analyze patterns
        has_prefix = sum(1 for m in messages if ':' in m and m.index(':') < 20)
        avg_length = sum(len(m) for m in messages) / len(messages) if messages else 0

        return {
            'analyzed': True,
            'sample_count': len(messages),
            'prefix_usage_percent': (has_prefix / len(messages) * 100) if messages else 0,
            'average_length': int(avg_length)
        }
    except:
        return {'analyzed': False}


