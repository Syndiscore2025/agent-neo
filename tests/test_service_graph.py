"""
Tests for the dependency-free service/dependency graph analyzer
(app/modules/service_graph.py) and its surfacing via the context engine.
"""

import importlib

import pytest

from app.modules.service_graph import build_service_graph, MAX_NODES


def _node_by_name(nodes, name):
    for nd in nodes:
        if nd["name"] == name:
            return nd
    return None


class TestManifestParsing:
    def test_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "web", "dependencies": {"react": "^18", "axios": "^1"}}'
        )
        nodes = build_service_graph(str(tmp_path))["nodes"]
        node = _node_by_name(nodes, "web")
        assert node and node["kind"] == "node"
        assert "react" in node["key_dependencies"]
        assert "axios" in node["key_dependencies"]

    def test_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "fastapi==0.110.0\n# comment\n-e .\nuvicorn>=0.20\n"
        )
        nodes = build_service_graph(str(tmp_path))["nodes"]
        assert nodes and nodes[0]["kind"] == "python"
        deps = nodes[0]["key_dependencies"]
        assert "fastapi" in deps and "uvicorn" in deps
        assert "-e" not in deps  # comment / option lines skipped

    def test_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "svc"\n'
            'dependencies = ["httpx>=0.27", "pydantic==2.5"]\n'
        )
        nodes = build_service_graph(str(tmp_path))["nodes"]
        node = _node_by_name(nodes, "svc")
        assert node and node["kind"] == "python"
        assert "httpx" in node["key_dependencies"]
        assert "pydantic" in node["key_dependencies"]

    def test_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.11-slim\nRUN pip install .\n"
        )
        nodes = build_service_graph(str(tmp_path))["nodes"]
        assert nodes and nodes[0]["kind"] == "docker"
        assert nodes[0]["key_dependencies"] == ["python:3.11-slim"]


class TestCompose:
    def test_depends_on_list_and_block(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    image: nginx:latest\n"
            "    depends_on:\n"
            "      - api\n"
            "      - db\n"
            "  api:\n"
            "    image: my/api:1.0\n"
            "    depends_on: [db]\n"
            "  db:\n"
            "    image: postgres:16\n"
        )
        nodes = build_service_graph(str(tmp_path))["nodes"]
        names = {nd["name"] for nd in nodes}
        assert {"web", "api", "db"} <= names
        web = _node_by_name(nodes, "web")
        assert web["depends_on"] == ["api", "db"]
        assert web["key_dependencies"] == ["nginx:latest"]
        api = _node_by_name(nodes, "api")
        assert api["depends_on"] == ["db"]
        db = _node_by_name(nodes, "db")
        assert db["depends_on"] == []


class TestAggregation:
    def test_summary_reports_nodes_and_edges(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "web"}')
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  a:\n    depends_on:\n      - b\n  b:\n    image: x\n"
        )
        graph = build_service_graph(str(tmp_path))
        assert graph["summary"]
        assert "node(s)" in graph["summary"]
        assert "dependency edge(s)" in graph["summary"]

    def test_skips_vendored_dirs(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package.json").write_text(
            '{"name": "vendored"}'
        )
        (tmp_path / "package.json").write_text('{"name": "real"}')
        nodes = build_service_graph(str(tmp_path))["nodes"]
        assert _node_by_name(nodes, "real")
        assert _node_by_name(nodes, "vendored") is None

    def test_bounded_to_max_nodes(self, tmp_path):
        for i in range(MAX_NODES + 10):
            d = tmp_path / f"svc{i}"
            d.mkdir()
            (d / "requirements.txt").write_text("flask\n")
        nodes = build_service_graph(str(tmp_path))["nodes"]
        assert len(nodes) <= MAX_NODES

    def test_empty_repo_returns_no_nodes(self, tmp_path):
        graph = build_service_graph(str(tmp_path))
        assert graph["nodes"] == []
        assert graph["summary"] == ""


class TestContextEngineSurfacing:
    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NEO_DISABLE_EMBEDDINGS", "1")
        monkeypatch.setenv("NEO_DATA_DIR", str(tmp_path / "_neo_data"))
        from app.modules import managed_repos, repo_index
        repo_index.reset_repo_index_cache()
        managed_repos.reset_managed_repo_registry()
        yield
        repo_index.reset_repo_index_cache()
        managed_repos.reset_managed_repo_registry()

    def test_graph_attached_to_context_pack(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "web"}')
        from app.interactive.context_engine import ContextEngine

        engine = ContextEngine(str(tmp_path))
        pack = engine.build_context_pack("update the web service")

        assert pack.service_graph is not None
        assert any(n.name == "web" for n in pack.service_graph.nodes)
        assert "stack:" in pack.summary
