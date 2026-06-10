"""
AGENT NEO - Persistent Repository Index
A single, shared, on-disk index per repository:
  - file inventory (size, mtime, hash, language, test/convention flags)
  - chunk store for search (40-line chunks)
  - optional embedding vectors (sentence-transformers, graceful fallback)
Persisted under <repo>/.neo/index/ and updated incrementally.
"""

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_LINES = 40

INDEXED_SUFFIXES = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".md"}
CONVENTION_NAMES = {
    "settings.py", "config.py", "conftest.py", "setup.py",
    "pyproject.toml", "package.json", "tsconfig.json", "Makefile",
    "requirements.txt", "Dockerfile", "docker-compose.yml",
}
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".neo",
}

_LANGUAGE_BY_SUFFIX = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".go": "go",
    ".rs": "rust", ".md": "markdown",
}


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _is_test_path(rel_path: str) -> bool:
    p = Path(rel_path)
    name = p.name.lower()
    if name.startswith("test_") or name.startswith("test."):
        return True
    stem = p.stem.lower()
    if stem.endswith("_test") or stem.endswith(".test") or stem.endswith(".spec"):
        return True
    return any(part.lower() in ("tests", "test", "__tests__") for part in p.parts[:-1])


class RepoIndex:
    """
    Persistent, incrementally-updated index of a repository.

    One instance per repo path (use get_repo_index()). Thread-safe refresh.
    Embeddings are optional; keyword search over stored chunks is the fallback.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self._lock = threading.Lock()
        self._files: Dict[str, dict] = {}
        self._chunks: List[dict] = []      # {path, start_line, text}
        self._vectors = None               # np.ndarray row-aligned with _chunks
        self._embed_model = None
        self._embed_attempted = False
        self._loaded = False
        self.persist_dir = self._resolve_persist_dir()

    # ── persistence ──────────────────────────────────────────────────────────

    def _resolve_persist_dir(self) -> Optional[Path]:
        """Return .neo/index/ dir, or None if .neo exists as a guidelines file."""
        neo = self.repo_path / ".neo"
        if neo.exists() and neo.is_file():
            logger.warning(
                f"{neo} is a file (guidelines convention); "
                "RepoIndex will run in-memory only"
            )
            return None
        return neo / "index"

    def _load_persisted(self) -> None:
        if self.persist_dir is None:
            return
        manifest_path = self.persist_dir / "manifest.json"
        chunks_path = self.persist_dir / "chunks.json"
        if not manifest_path.exists() or not chunks_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != INDEX_VERSION:
                return
            self._files = manifest.get("files", {})
            self._chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            vectors_path = self.persist_dir / "vectors.npy"
            if vectors_path.exists() and manifest.get("embed_model") == EMBED_MODEL_NAME:
                try:
                    import numpy as np
                    vectors = np.load(str(vectors_path))
                    if len(vectors) == len(self._chunks):
                        self._vectors = vectors
                except Exception as exc:
                    logger.warning(f"Could not load index vectors: {exc}")
            logger.info(
                f"RepoIndex loaded: {len(self._files)} files, "
                f"{len(self._chunks)} chunks"
            )
        except Exception as exc:
            logger.warning(f"Could not load persisted index, rebuilding: {exc}")
            self._files = {}
            self._chunks = []
            self._vectors = None

    def _persist(self) -> None:
        if self.persist_dir is None:
            return
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "version": INDEX_VERSION,
                "embed_model": EMBED_MODEL_NAME if self._vectors is not None else None,
                "files": self._files,
            }
            (self.persist_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=1), encoding="utf-8"
            )
            (self.persist_dir / "chunks.json").write_text(
                json.dumps(self._chunks), encoding="utf-8"
            )
            if self._vectors is not None:
                import numpy as np
                np.save(str(self.persist_dir / "vectors.npy"), self._vectors)
        except Exception as exc:
            logger.warning(f"Could not persist index: {exc}")

    # ── scanning / incremental refresh ───────────────────────────────────────

    def _scan_disk(self) -> Dict[str, dict]:
        """Inventory of indexable files currently on disk: {rel: {size, mtime}}."""
        found: Dict[str, dict] = {}
        for fpath in self.repo_path.rglob("*"):
            if not fpath.is_file():
                continue
            if any(p in fpath.parts for p in _SKIP_DIRS):
                continue
            if fpath.suffix not in INDEXED_SUFFIXES and fpath.name not in CONVENTION_NAMES:
                continue
            try:
                stat = fpath.stat()
            except OSError:
                continue
            rel = fpath.relative_to(self.repo_path).as_posix()
            found[rel] = {"size": stat.st_size, "mtime": stat.st_mtime}
        return found

    def refresh(self) -> dict:
        """
        Bring the index up to date. First call loads persisted data; every call
        re-indexes only changed/new files and drops deleted ones.

        Returns stats: {"added": n, "updated": n, "removed": n, "reused": n}.
        """
        with self._lock:
            if not self._loaded:
                self._load_persisted()
                self._loaded = True

            on_disk = self._scan_disk()
            stats = {"added": 0, "updated": 0, "removed": 0, "reused": 0}
            changed_paths: List[str] = []

            for rel, info in on_disk.items():
                known = self._files.get(rel)
                if known and known["size"] == info["size"] and known["mtime"] == info["mtime"]:
                    stats["reused"] += 1
                    continue
                try:
                    text = (self.repo_path / rel).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except Exception:
                    continue
                sha = _sha1(text)
                if known and known.get("sha1") == sha:
                    # touched but unchanged — update stat info only
                    known.update(info)
                    stats["reused"] += 1
                    continue
                stats["updated" if known else "added"] += 1
                self._files[rel] = {
                    **info,
                    "sha1": sha,
                    "language": _LANGUAGE_BY_SUFFIX.get(Path(rel).suffix, "other"),
                    "is_test": _is_test_path(rel),
                    "is_convention": Path(rel).name in CONVENTION_NAMES,
                }
                changed_paths.append(rel)
                self._replace_chunks(rel, text)

            removed = [rel for rel in list(self._files) if rel not in on_disk]
            for rel in removed:
                del self._files[rel]
                self._drop_chunks(rel)
                stats["removed"] += 1

            if changed_paths or removed:
                self._update_vectors()
                self._persist()
            return stats

    def _replace_chunks(self, rel: str, text: str) -> None:
        self._drop_chunks(rel)
        lines = text.splitlines()
        for i in range(0, len(lines), CHUNK_LINES):
            chunk = "\n".join(lines[i:i + CHUNK_LINES])
            if chunk.strip():
                self._chunks.append({"path": rel, "start_line": i + 1, "text": chunk})

    def _drop_chunks(self, rel: str) -> None:
        # Vectors are aligned with the first len(self._vectors) chunks; chunks
        # appended later in the same refresh have no vectors yet.
        if self._vectors is not None:
            n = len(self._vectors)
            keep = [i for i, c in enumerate(self._chunks[:n]) if c["path"] != rel]
            if len(keep) != n:
                self._vectors = self._vectors[keep]
        self._chunks = [c for c in self._chunks if c["path"] != rel]

    # ── embeddings ───────────────────────────────────────────────────────────

    def _ensure_embedder(self) -> bool:
        """Lazily load the embedding model. Returns True if usable."""
        if self._embed_model is not None:
            return True
        if self._embed_attempted:
            return False
        self._embed_attempted = True
        if os.getenv("NEO_DISABLE_EMBEDDINGS"):
            logger.info("Embeddings disabled via NEO_DISABLE_EMBEDDINGS")
            return False
        try:
            from sentence_transformers import SentenceTransformer
            self._embed_model = SentenceTransformer(EMBED_MODEL_NAME)
            return True
        except Exception as exc:
            logger.info(f"Embeddings unavailable ({exc}); using keyword search")
            return False

    @property
    def embeddings_available(self) -> bool:
        return self._ensure_embedder()

    def _update_vectors(self) -> None:
        """(Re)embed chunks. Only newly appended chunks are encoded when possible."""
        if not self._ensure_embedder():
            self._vectors = None
            return
        try:
            import numpy as np
            if self._vectors is not None and len(self._vectors) <= len(self._chunks):
                # Chunks for changed files were appended at the tail by
                # _replace_chunks; encode only that un-embedded tail.
                tail = self._chunks[len(self._vectors):]
                if tail:
                    embs = np.asarray(self._embed_model.encode(
                        [c["text"] for c in tail],
                        normalize_embeddings=True, show_progress_bar=False,
                    ), dtype="float32")
                    self._vectors = np.vstack([self._vectors, embs])
                return
            # Full (re)build: vector store missing or misaligned
            texts = [c["text"] for c in self._chunks]
            if texts:
                self._vectors = np.asarray(self._embed_model.encode(
                    texts, normalize_embeddings=True, show_progress_bar=False
                ), dtype="float32")
            else:
                self._vectors = None
        except Exception as exc:
            logger.warning(f"Embedding update failed: {exc}")
            self._vectors = None


    # ── query API ────────────────────────────────────────────────────────────

    def search(self, task_text: str, k: int = 10) -> List[dict]:
        """
        Rank files relevant to `task_text`.

        Returns up to `k` results: {path, score, reason, snippet}.
        Semantic search when embeddings are available, keyword scoring otherwise.
        """
        self.refresh()
        if not self._chunks:
            return []
        head = task_text.strip().replace("\n", " ")[:60]

        if self._vectors is not None and self._ensure_embedder():
            try:
                import numpy as np
                q = self._embed_model.encode([task_text], normalize_embeddings=True)[0]
                sims = np.dot(self._vectors, q)
                best: Dict[str, tuple] = {}  # path -> (score, chunk_idx)
                for i, sim in enumerate(sims):
                    path = self._chunks[i]["path"]
                    if path not in best or sim > best[path][0]:
                        best[path] = (float(sim), i)
                ranked = sorted(best.items(), key=lambda x: x[1][0], reverse=True)
                return [
                    {
                        "path": path,
                        "score": round(score, 4),
                        "reason": f"semantic match for '{head}' (score={score:.2f})",
                        "snippet": self._chunks[idx]["text"][:200],
                    }
                    for path, (score, idx) in ranked[:k]
                ]
            except Exception as exc:
                logger.warning(f"Semantic search failed, using keywords: {exc}")

        return self._keyword_search(task_text, k)

    def _keyword_search(self, task_text: str, k: int) -> List[dict]:
        keywords = [w.lower() for w in task_text.split() if len(w) > 3][:8]
        if not keywords:
            return []
        scores: Dict[str, dict] = {}  # path -> {hits, by_kw, snippet}
        for chunk in self._chunks:
            text_lower = chunk["text"].lower()
            for kw in keywords:
                n = text_lower.count(kw)
                if n:
                    entry = scores.setdefault(
                        chunk["path"], {"hits": 0, "by_kw": {}, "snippet": chunk["text"][:200]}
                    )
                    entry["hits"] += n
                    entry["by_kw"][kw] = entry["by_kw"].get(kw, 0) + n
        # Filename matches get a strong boost
        for path in self._files:
            name_lower = Path(path).name.lower()
            for kw in keywords:
                if kw in name_lower:
                    entry = scores.setdefault(
                        path, {"hits": 0, "by_kw": {}, "snippet": ""}
                    )
                    entry["hits"] += 10
                    entry["by_kw"][kw] = entry["by_kw"].get(kw, 0) + 1
        ranked = sorted(scores.items(), key=lambda x: x[1]["hits"], reverse=True)
        results = []
        for path, entry in ranked[:k]:
            top_kw, top_n = max(entry["by_kw"].items(), key=lambda x: x[1])
            results.append({
                "path": path,
                "score": float(entry["hits"]),
                "reason": f"keyword match: '{top_kw}' ({top_n} hit{'s' if top_n != 1 else ''})",
                "snippet": entry["snippet"],
            })
        return results

    def summarize(self) -> dict:
        """High-level index summary."""
        self.refresh()
        languages: Dict[str, int] = {}
        test_files = 0
        for meta in self._files.values():
            languages[meta["language"]] = languages.get(meta["language"], 0) + 1
            if meta["is_test"]:
                test_files += 1
        return {
            "total_files": len(self._files),
            "total_chunks": len(self._chunks),
            "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
            "test_files": test_files,
            "embeddings_available": self._vectors is not None,
            "persisted": self.persist_dir is not None,
        }

    def get_file_metadata(self, path: str) -> Optional[dict]:
        """Metadata for one indexed file (language, is_test, is_convention, …)."""
        if not self._loaded:
            self.refresh()
        return self._files.get(Path(path).as_posix())


# ── shared per-repo instances ─────────────────────────────────────────────────
_INDEX_CACHE: Dict[str, RepoIndex] = {}
_CACHE_LOCK = threading.Lock()


def get_repo_index(repo_path: str) -> RepoIndex:
    """Return the single shared RepoIndex for a repo path (process-wide)."""
    key = str(Path(repo_path).resolve())
    with _CACHE_LOCK:
        if key not in _INDEX_CACHE:
            _INDEX_CACHE[key] = RepoIndex(key)
        return _INDEX_CACHE[key]


def reset_repo_index_cache() -> None:
    """Clear cached indexes (intended for tests)."""
    with _CACHE_LOCK:
        _INDEX_CACHE.clear()
