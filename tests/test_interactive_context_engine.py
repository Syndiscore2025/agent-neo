"""
Tests for interactive context engine.
"""

import pytest
from pathlib import Path
from app.interactive.context_engine import ContextEngine
from app.interactive.contracts import ChatContext


class TestContextEngine:
    """Test context engine functionality."""
    
    def test_initialization(self, tmp_path):
        """Test context engine initialization."""
        engine = ContextEngine(str(tmp_path))
        assert engine.repo_path == tmp_path
        assert engine._repo_cache is None
        assert engine._file_cache == {}
    
    def test_gather_context_basic(self, tmp_path):
        """Test basic context gathering."""
        engine = ContextEngine(str(tmp_path))
        context = engine.gather_context()
        
        assert "repo_path" in context
        assert "current_file" in context
        assert "repo_summary" in context
    
    def test_gather_context_with_chat_context(self, tmp_path):
        """Test context gathering with ChatContext."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        engine = ContextEngine(str(tmp_path))
        chat_context = ChatContext(
            current_file="test.py",
            current_file_content="print('hello')",
            selected_code=None,
            language="python"
        )
        
        context = engine.gather_context(chat_context)
        
        assert context["current_file"] == "test.py"
        assert context["current_file_content"] == "print('hello')"
        assert context["language"] == "python"
    
    def test_extract_imports_python(self, tmp_path):
        """Test Python import extraction."""
        engine = ContextEngine(str(tmp_path))
        
        content = """
import os
from pathlib import Path
from app.core import engine
"""
        
        imports = engine._extract_imports(content, '.py')
        
        assert "os.py" in imports
        assert "pathlib.py" in imports
        assert "app/core.py" in imports
    
    def test_extract_imports_typescript(self, tmp_path):
        """Test TypeScript import extraction."""
        engine = ContextEngine(str(tmp_path))
        
        content = """
import { Component } from './component';
import * as utils from '../utils';
"""
        
        imports = engine._extract_imports(content, '.ts')
        
        assert './component' in imports
        assert '../utils' in imports
    
    def test_find_test_file(self, tmp_path):
        """Test finding corresponding test file."""
        # Create source and test files
        (tmp_path / "module.py").write_text("def foo(): pass")
        (tmp_path / "test_module.py").write_text("def test_foo(): pass")
        
        engine = ContextEngine(str(tmp_path))
        test_file = engine._find_test_file("module.py")
        
        assert test_file == "test_module.py"
    
    def test_find_files_in_same_directory(self, tmp_path):
        """Test finding files in same directory."""
        # Create multiple files
        (tmp_path / "file1.py").write_text("pass")
        (tmp_path / "file2.py").write_text("pass")
        (tmp_path / "file3.py").write_text("pass")
        
        engine = ContextEngine(str(tmp_path))
        files = engine._find_files_in_same_directory("file1.py")
        
        assert "file2.py" in files
        assert "file3.py" in files
        assert "file1.py" not in files  # Should not include itself
    
    def test_truncate_content(self, tmp_path):
        """Test content truncation."""
        engine = ContextEngine(str(tmp_path))
        engine.max_context_lines = 10

        # Create content with 20 lines
        content = "\n".join([f"line {i}" for i in range(20)])

        truncated = engine._truncate_content(content)
        lines = truncated.splitlines()

        assert len(lines) <= 12  # 10 lines + blank line + truncation message
        assert "truncated" in truncated.lower()
    
    def test_build_prompt_context(self, tmp_path):
        """Test prompt context building."""
        engine = ContextEngine(str(tmp_path))
        
        context = {
            "repo_summary": {
                "total_files": 100,
                "total_lines": 5000,
                "languages": ["Python", "TypeScript"]
            },
            "current_file": "test.py",
            "selected_code": "print('hello')"
        }
        
        prompt = engine.build_prompt_context(context)
        
        assert "100 files" in prompt
        assert "5000 lines" in prompt
        assert "test.py" in prompt
        assert "print('hello')" in prompt

