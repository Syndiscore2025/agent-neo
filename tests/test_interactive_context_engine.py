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


class TestBuildContextPack:
    """Tests for the task-aware context pack (Phase B)."""

    @pytest.fixture(autouse=True)
    def _isolated_index(self, monkeypatch, tmp_path):
        from app.modules.repo_index import reset_repo_index_cache
        from app.modules.managed_repos import reset_managed_repo_registry
        monkeypatch.setenv("NEO_DISABLE_EMBEDDINGS", "1")
        monkeypatch.setenv("NEO_DATA_DIR", str(tmp_path / "_neo_data"))
        reset_repo_index_cache()
        reset_managed_repo_registry()
        yield
        reset_repo_index_cache()
        reset_managed_repo_registry()

    def _make_repo(self, tmp_path):
        (tmp_path / "payments.py").write_text(
            "def payment_schedule():\n    '''payments schedule'''\n    return []\n"
        )
        (tmp_path / "module.py").write_text("from payments import payment_schedule\n")
        (tmp_path / "test_module.py").write_text("def test_module(): pass\n")
        (tmp_path / "other.py").write_text("x = 1\n")
        return tmp_path

    def test_pack_is_bounded_and_every_file_has_a_reason(self, tmp_path):
        repo = self._make_repo(tmp_path)
        for i in range(30):
            (repo / f"payments_extra_{i}.py").write_text("# payments helper\n")

        engine = ContextEngine(str(repo))
        pack = engine.build_context_pack("improve the payments code")

        all_files = pack.primary_files + pack.supporting_files
        assert 0 < len(all_files) <= engine.max_pack_files
        assert len(pack.primary_files) <= engine.max_primary_files
        assert all(f.reason for f in all_files)
        assert pack.summary

    def test_active_file_heuristics_with_reasons(self, tmp_path):
        repo = self._make_repo(tmp_path)
        engine = ContextEngine(str(repo))
        chat_context = ChatContext(
            current_file="module.py",
            current_file_content="from payments import payment_schedule\n",
        )

        pack = engine.build_context_pack("refactor module", chat_context)
        all_files = pack.primary_files + pack.supporting_files
        by_path = {f.path: f for f in all_files}

        assert pack.primary_files[0].path == "module.py"
        assert pack.primary_files[0].reason == "active file in editor"
        assert "payments.py" in by_path
        assert by_path["payments.py"].source in ("import", "semantic", "keyword")
        assert "test_module.py" in by_path
        assert "test file" in by_path["test_module.py"].reason

    def test_task_keywords_surface_expected_files(self, tmp_path):
        repo = self._make_repo(tmp_path)
        engine = ContextEngine(str(repo))

        pack = engine.build_context_pack("fix the payments schedule bug")
        all_paths = [f.path for f in pack.primary_files + pack.supporting_files]

        assert "payments.py" in all_paths

    def test_fallback_when_repo_index_unavailable(self, tmp_path, monkeypatch):
        import app.modules.repo_index as repo_index_mod

        def boom(_path):
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(repo_index_mod, "get_repo_index", boom)

        repo = self._make_repo(tmp_path)
        engine = ContextEngine(str(repo))
        chat_context = ChatContext(
            current_file="module.py",
            current_file_content="from payments import payment_schedule\n",
        )

        pack = engine.build_context_pack("refactor module", chat_context)
        all_files = pack.primary_files + pack.supporting_files

        assert all_files  # heuristics-only pack still produced
        assert all_files[0].path == "module.py"
        assert all(f.source in ("active_file", "import", "test_file", "sibling")
                   for f in all_files)

