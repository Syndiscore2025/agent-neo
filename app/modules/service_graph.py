"""
AGENT NEO - Service / Dependency Graph
A lightweight, dependency-free analyzer that parses common manifests into a
coarse service/dependency graph for a repo:
  package.json, requirements.txt, pyproject.toml, docker-compose(.yml/.yaml),
  compose(.yml/.yaml), Dockerfile.
Surfaced in the context pack so the agent understands cross-service structure.
Best-effort: any parse failure is skipped, never raised.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_NODES = 40
_TOP_DEPS = 6
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".next", ".neo", ".heroku", "site-packages", ".mypy_cache", ".pytest_cache",
    ".cache",
}
_MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml",
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "Dockerfile",
}
_REQ_SPLIT = re.compile(r"[<>=!~\[ ;]")


def _rel(root: Path, p: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.name


def _node_name(root: Path, manifest: Path, default: str) -> str:
    parent = manifest.parent
    if parent == root:
        return root.name or default
    return parent.name


def _iter_manifests(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or p.name not in _MANIFESTS:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        yield p


def _parse_package_json(root: Path, p: Path) -> Optional[dict]:
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    deps = list((data.get("dependencies") or {}).keys())
    return {
        "name": data.get("name") or _node_name(root, p, "node-app"),
        "kind": "node",
        "manifest": _rel(root, p),
        "depends_on": [],
        "key_dependencies": deps[:_TOP_DEPS],
    }


def _parse_requirements(root: Path, p: Path) -> Optional[dict]:
    deps: List[str] = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            name = _REQ_SPLIT.split(line, 1)[0].strip()
            if name:
                deps.append(name)
    except Exception:
        return None
    return {
        "name": _node_name(root, p, "python-app"),
        "kind": "python",
        "manifest": _rel(root, p),
        "depends_on": [],
        "key_dependencies": deps[:_TOP_DEPS],
    }


def _parse_pyproject(root: Path, p: Path) -> Optional[dict]:
    name: Optional[str] = None
    deps: List[str] = []
    try:
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8", errors="replace"))
        project = data.get("project") or {}
        name = project.get("name")
        for d in project.get("dependencies") or []:
            deps.append(_REQ_SPLIT.split(d, 1)[0].strip())
        poetry = (data.get("tool") or {}).get("poetry") or {}
        name = name or poetry.get("name")
        for dep in poetry.get("dependencies") or {}:
            if dep.lower() != "python":
                deps.append(dep)
    except Exception:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'^name\s*=\s*[\'"]([^\'"]+)[\'"]', txt, re.MULTILINE)
            if m:
                name = m.group(1)
        except Exception:
            return None
    return {
        "name": name or _node_name(root, p, "python-app"),
        "kind": "python",
        "manifest": _rel(root, p),
        "depends_on": [],
        "key_dependencies": [d for d in deps if d][:_TOP_DEPS],
    }


def _parse_dockerfile(root: Path, p: Path) -> Optional[dict]:
    base: Optional[str] = None
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.upper().startswith("FROM "):
                base = s.split()[1]
                break
    except Exception:
        return None
    return {
        "name": _node_name(root, p, "service") + " (docker)",
        "kind": "docker",
        "manifest": _rel(root, p),
        "depends_on": [],
        "key_dependencies": [base] if base else [],
    }


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def _parse_compose(root: Path, p: Path) -> List[dict]:
    """Indentation-based parse of a compose file's services + depends_on/image."""
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    rel = _rel(root, p)
    nodes: Dict[str, dict] = {}
    svc_indent: Optional[int] = None
    entry_indent: Optional[int] = None
    cur: Optional[str] = None
    in_depends = False

    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip() == "services:":
            svc_indent = _indent(lines[i])
            i += 1
            break
        i += 1
    if svc_indent is None:
        return []

    while i < n:
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        cind = _indent(raw)
        stripped = raw.strip()
        if cind <= svc_indent:
            break
        if entry_indent is None:
            entry_indent = cind
        if cind == entry_indent and stripped.endswith(":"):
            cur = stripped[:-1].strip()
            nodes[cur] = {
                "name": cur, "kind": "compose-service", "manifest": rel,
                "depends_on": [], "key_dependencies": [],
            }
            in_depends = False
            continue
        if cur is None:
            continue
        if stripped.startswith("image:"):
            img = stripped.split(":", 1)[1].strip().strip("\"'")
            if img:
                nodes[cur]["key_dependencies"] = [img]
            in_depends = False
        elif stripped.startswith("depends_on:"):
            rest = stripped.split(":", 1)[1].strip()
            if rest.startswith("[") and rest.endswith("]"):
                for d in rest[1:-1].split(","):
                    d = d.strip().strip("\"'")
                    if d:
                        nodes[cur]["depends_on"].append(d)
                in_depends = False
            else:
                in_depends = True
        elif in_depends and stripped.startswith("- "):
            d = stripped[2:].strip().strip("\"'")
            if d:
                nodes[cur]["depends_on"].append(d)
        elif cind <= entry_indent + 2:
            in_depends = False
    return list(nodes.values())


def _summarize(nodes: List[dict]) -> str:
    if not nodes:
        return ""
    kinds: Dict[str, int] = {}
    for nd in nodes:
        kinds[nd["kind"]] = kinds.get(nd["kind"], 0) + 1
    kind_str = ", ".join(f"{v} {k}" for k, v in kinds.items())
    edges = sum(len(nd.get("depends_on") or []) for nd in nodes)
    head = f"{len(nodes)} service/manifest node(s) [{kind_str}]"
    if edges:
        head += f", {edges} dependency edge(s)"
    parts: List[str] = []
    for nd in nodes[:6]:
        dep = nd.get("depends_on") or []
        parts.append(f"{nd['name']}\u2192{','.join(dep[:3])}" if dep else nd["name"])
    return f"{head}. " + "; ".join(parts)


def build_service_graph(repo_path: str) -> dict:
    """
    Parse a repo's manifests into {'nodes': [...], 'summary': str}.

    Each node: {name, kind, manifest, depends_on, key_dependencies}.
    Bounded to MAX_NODES; never raises.
    """
    root = Path(repo_path).resolve()
    nodes: List[dict] = []
    for p in _iter_manifests(root):
        if len(nodes) >= MAX_NODES:
            break
        try:
            name = p.name
            if name == "package.json":
                node = _parse_package_json(root, p)
                if node:
                    nodes.append(node)
            elif name == "requirements.txt":
                node = _parse_requirements(root, p)
                if node:
                    nodes.append(node)
            elif name == "pyproject.toml":
                node = _parse_pyproject(root, p)
                if node:
                    nodes.append(node)
            elif name == "Dockerfile":
                node = _parse_dockerfile(root, p)
                if node:
                    nodes.append(node)
            else:
                nodes.extend(_parse_compose(root, p))
        except Exception as exc:
            logger.debug(f"service_graph: failed to parse {p}: {exc}")
    nodes = nodes[:MAX_NODES]
    return {"nodes": nodes, "summary": _summarize(nodes)}
