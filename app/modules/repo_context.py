"""
AGENT NEO - Repository Context
Scan repository and gather context.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional


def scan_repository(repo_path: str) -> Dict:
    """
    Scan repository and gather context.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Dictionary with repository information
    """
    repo = Path(repo_path)
    
    if not repo.exists():
        return {"error": "Repository path does not exist"}
    
    info = {
        "path": str(repo),
        "files": [],
        "directories": [],
        "languages": set(),
        "has_tests": False,
        "has_ci": False,
        "total_files": 0,
        "total_lines": 0
    }
    
    # Scan directory structure
    for root, dirs, files in os.walk(repo):
        # Skip hidden directories and common ignore patterns
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'env']]
        
        rel_root = Path(root).relative_to(repo)
        
        for file in files:
            if file.startswith('.'):
                continue
            
            file_path = Path(root) / file
            rel_path = file_path.relative_to(repo)
            
            info["files"].append(str(rel_path))
            info["total_files"] += 1
            
            # Detect language
            ext = file_path.suffix
            if ext:
                info["languages"].add(ext)
            
            # Check for tests
            if 'test' in file.lower() or 'spec' in file.lower():
                info["has_tests"] = True
            
            # Count lines
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    info["total_lines"] += sum(1 for _ in f)
            except:
                pass
    
    # Check for CI/CD
    ci_indicators = ['.github/workflows', '.gitlab-ci.yml', '.circleci', 'Jenkinsfile']
    for indicator in ci_indicators:
        if (repo / indicator).exists():
            info["has_ci"] = True
            break
    
    info["languages"] = list(info["languages"])
    
    return info


def file_exists(repo_path: str, file_path: str) -> bool:
    """
    Check if file exists in repository.
    
    Args:
        repo_path: Path to repository
        file_path: Relative path to file
        
    Returns:
        True if file exists
    """
    full_path = Path(repo_path) / file_path
    return full_path.exists() and full_path.is_file()


def get_file_content(repo_path: str, file_path: str) -> Optional[str]:
    """
    Get content of a file.
    
    Args:
        repo_path: Path to repository
        file_path: Relative path to file
        
    Returns:
        File content or None if not found
    """
    full_path = Path(repo_path) / file_path
    
    if not full_path.exists():
        return None
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None


def find_files_by_pattern(repo_path: str, pattern: str) -> List[str]:
    """
    Find files matching a pattern.
    
    Args:
        repo_path: Path to repository
        pattern: Glob pattern
        
    Returns:
        List of matching file paths
    """
    repo = Path(repo_path)
    matches = []
    
    for file_path in repo.rglob(pattern):
        if file_path.is_file():
            rel_path = file_path.relative_to(repo)
            matches.append(str(rel_path))
    
    return matches


def get_directory_structure(repo_path: str, max_depth: int = 3) -> Dict:
    """
    Get directory structure up to max depth.
    
    Args:
        repo_path: Path to repository
        max_depth: Maximum depth to traverse
        
    Returns:
        Dictionary representing directory structure
    """
    repo = Path(repo_path)
    
    def _build_tree(path: Path, current_depth: int) -> Dict:
        if current_depth > max_depth:
            return {}
        
        tree = {
            "name": path.name,
            "type": "directory" if path.is_dir() else "file",
            "children": []
        }
        
        if path.is_dir():
            try:
                for child in sorted(path.iterdir()):
                    if child.name.startswith('.'):
                        continue
                    if child.name in ['node_modules', '__pycache__', 'venv', 'env']:
                        continue
                    tree["children"].append(_build_tree(child, current_depth + 1))
            except PermissionError:
                pass
        
        return tree
    
    return _build_tree(repo, 0)

