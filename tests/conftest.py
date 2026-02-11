"""
AGENT NEO - Test Fixtures
"""

import pytest
import tempfile
import shutil
import subprocess
import os
import stat
import time
from pathlib import Path


def _remove_readonly(func, path, excinfo):
    """Error handler for shutil.rmtree on Windows."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir) / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=repo_path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo_path, check=True)
    subprocess.run(['git', 'checkout', '-b', 'main'], cwd=repo_path, check=True, capture_output=True)

    # Create initial commit
    test_file = repo_path / "test.py"
    test_file.write_text("# Test file\n\ndef hello():\n    return 'world'\n")
    subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=repo_path, check=True)

    yield str(repo_path)

    # Cleanup with retry for Windows file locking issues
    for attempt in range(3):
        try:
            shutil.rmtree(temp_dir, onerror=_remove_readonly)
            break
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))


@pytest.fixture
def sample_diff():
    """Sample unified diff for testing."""
    return """--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file
 
 def hello():
-    return 'world'
+    print('Hello')
+    return 'world'
"""


@pytest.fixture
def invalid_diff():
    """Invalid diff for testing."""
    return """This is not a valid diff
Just some random text
"""


@pytest.fixture
def large_diff():
    """Large diff that exceeds limits."""
    lines = ["--- a/test.py\n", "+++ b/test.py\n", "@@ -1,10 +1,2011 @@\n"]
    for i in range(2001):
        lines.append(f"+Line {i}\n")
    return ''.join(lines)


@pytest.fixture
def forbidden_diff():
    """Diff with forbidden patterns."""
    return """--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file
 
 def dangerous():
+    subprocess.run(['git', 'reset', '--hard'])
+    return 'danger'
"""


@pytest.fixture
def multi_file_diff():
    """Diff affecting multiple files."""
    return """--- a/file1.py
+++ b/file1.py
@@ -1,2 +1,3 @@
 # File 1
+# Modified
 
--- a/file2.py
+++ b/file2.py
@@ -1,2 +1,3 @@
 # File 2
+# Modified
 
"""

