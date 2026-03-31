"""File-backed integrations registry for Coding Matrix service bindings."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_DEFAULT_CATALOG: list[dict[str, Any]] = [
    {"provider": "github", "label": "GitHub", "description": "Repo tree, files, commits, pull requests.", "default_base_url": "https://api.github.com"},
    {"provider": "digitalocean", "label": "DigitalOcean", "description": "Apps, droplets, deployments, and platform APIs.", "default_base_url": "https://api.digitalocean.com/v2"},
    {"provider": "render", "label": "Render", "description": "Services, deploys, logs, and infrastructure APIs.", "default_base_url": "https://api.render.com/v1"},
    {"provider": "supabase", "label": "Supabase", "description": "Project REST APIs, auth, storage, and database tooling.", "default_base_url": "https://YOUR-PROJECT.supabase.co"},
    {"provider": "vercel", "label": "Vercel", "description": "Deployments, projects, and preview environments.", "default_base_url": "https://api.vercel.com"},
    {"provider": "linear", "label": "Linear", "description": "Issues, projects, and workflow automation.", "default_base_url": "https://api.linear.app"},
    {"provider": "notion", "label": "Notion", "description": "Docs, pages, databases, and workspace content.", "default_base_url": "https://api.notion.com/v1"},
    {"provider": "slack", "label": "Slack", "description": "Channels, messages, workflows, and bot APIs.", "default_base_url": "https://slack.com/api"},
    {"provider": "stripe", "label": "Stripe", "description": "Billing, payments, subscriptions, and customers.", "default_base_url": "https://api.stripe.com/v1"},
    {"provider": "openai", "label": "OpenAI", "description": "LLM, embeddings, and responses APIs.", "default_base_url": "https://api.openai.com/v1"},
    {"provider": "anthropic", "label": "Anthropic", "description": "Claude models and tool-calling APIs.", "default_base_url": "https://api.anthropic.com/v1"},
    {"provider": "custom_api", "label": "Custom API", "description": "Any external HTTP service you want to bind into Coding Matrix.", "default_base_url": None},
]


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _default_registry_path() -> Path:
    configured = os.getenv("INTEGRATIONS_REGISTRY_PATH")
    if configured:
        return Path(configured)
    return Path.home() / ".agent-neo" / "integrations.json"


class IntegrationRegistry:
    """Persists service credentials/config on the backend, never the browser."""

    def __init__(self, storage_path: str | os.PathLike[str] | None = None):
        self.storage_path = Path(storage_path) if storage_path else _default_registry_path()
        self._lock = threading.RLock()

    def list_catalog(self) -> list[dict[str, Any]]:
        return list(_DEFAULT_CATALOG)

    def list_integrations(self) -> list[dict[str, Any]]:
        return [self._sanitize(item) for item in self._read_store()["integrations"]]

    def get_raw_integration(self, integration_id: str) -> dict[str, Any] | None:
        for item in self._read_store()["integrations"]:
            if item["id"] == integration_id:
                return item
        return None

    def get_integration(self, integration_id: str) -> dict[str, Any] | None:
        item = self.get_raw_integration(integration_id)
        return self._sanitize(item) if item else None

    def create_integration(self, payload: dict[str, Any]) -> dict[str, Any]:
        store = self._read_store()
        now = _utcnow_iso()
        record = self._build_record(payload, existing=None)
        record.update({"id": str(uuid.uuid4()), "created_at": now, "updated_at": now})
        store["integrations"].append(record)
        self._write_store(store)
        return self._sanitize(record)

    def update_integration(self, integration_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        store = self._read_store()
        for index, item in enumerate(store["integrations"]):
            if item["id"] != integration_id:
                continue
            updated = self._build_record(payload, existing=item)
            updated["id"] = integration_id
            updated["created_at"] = item["created_at"]
            updated["updated_at"] = _utcnow_iso()
            store["integrations"][index] = updated
            self._write_store(store)
            return self._sanitize(updated)
        return None

    def delete_integration(self, integration_id: str) -> bool:
        store = self._read_store()
        remaining = [item for item in store["integrations"] if item["id"] != integration_id]
        if len(remaining) == len(store["integrations"]):
            return False
        store["integrations"] = remaining
        self._write_store(store)
        return True

    def build_proxy_url(self, integration: dict[str, Any], proxy_path: str, query: str = "") -> str:
        base_url = (integration.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("Integration has no base URL configured")
        suffix = proxy_path.lstrip("/")
        url = f"{base_url}/{suffix}" if suffix else base_url
        return f"{url}?{query}" if query else url

    def build_proxy_headers(self, integration: dict[str, Any]) -> dict[str, str]:
        headers = {str(key): str(value) for key, value in (integration.get("headers") or {}).items()}
        auth_type = integration.get("auth_type", "bearer")
        auth_header = integration.get("auth_header", "Authorization")
        auth_scheme = integration.get("auth_scheme", "Bearer")
        secret = (integration.get("secret") or "").strip()
        if secret and auth_type != "none":
            headers[auth_header] = f"{auth_scheme} {secret}".strip() if auth_type == "bearer" and auth_scheme else secret
        headers.setdefault("User-Agent", "AGENT-NEO/Coding-Matrix")
        return headers

    def _build_record(self, payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
        existing_provider = (existing or {}).get("provider")
        provider = str(payload.get("provider") or existing_provider or "").strip().lower()
        if not provider:
            raise ValueError("provider is required")
        preset = next((item for item in _DEFAULT_CATALOG if item["provider"] == provider), {})
        existing_base_url = (existing or {}).get("base_url")
        base_url = payload.get("base_url") or existing_base_url or preset.get("default_base_url") or ""
        if base_url:
            parsed = urlparse(str(base_url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("base_url must be a valid http(s) URL")
        secret = (existing or {}).get("secret", "")
        if payload.get("clear_secret"):
            secret = ""
        elif isinstance(payload.get("secret"), str) and payload.get("secret").strip():
            secret = payload["secret"].strip()
        return {
            "provider": provider,
            "label": str(payload.get("label") or (existing or {}).get("label") or preset.get("label") or "").strip(),
            "base_url": str(base_url).strip() or None,
            "auth_type": payload.get("auth_type") or (existing or {}).get("auth_type") or preset.get("default_auth_type", "bearer"),
            "auth_header": str(payload.get("auth_header") or (existing or {}).get("auth_header") or preset.get("default_auth_header", "Authorization")).strip(),
            "auth_scheme": (payload.get("auth_scheme") if payload.get("auth_scheme") is not None else (existing or {}).get("auth_scheme", preset.get("default_auth_scheme", "Bearer"))),
            "secret": secret,
            "headers": {str(key): str(value) for key, value in (payload.get("headers") or (existing or {}).get("headers") or {}).items()},
            "metadata": dict(payload.get("metadata") or (existing or {}).get("metadata") or {}),
            "description": (payload.get("description") if payload.get("description") is not None else (existing or {}).get("description") or preset.get("description")),
        }

    def _sanitize(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in item.items() if key != "secret"
        } | {"secret_configured": bool((item.get("secret") or "").strip())}

    def _read_store(self) -> dict[str, Any]:
        self._ensure_store()
        with self._lock:
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {"version": 1, "integrations": []}
        data.setdefault("version", 1)
        data.setdefault("integrations", [])
        return data

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            try:
                os.chmod(self.storage_path, 0o600)
            except OSError:
                pass

    def _ensure_store(self) -> None:
        if self.storage_path.exists():
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_store({"version": 1, "integrations": []})


_registry: IntegrationRegistry | None = None
_registry_path: Path | None = None


def get_integration_registry() -> IntegrationRegistry:
    global _registry, _registry_path
    path = _default_registry_path()
    if _registry is None or _registry_path != path:
        _registry = IntegrationRegistry(path)
        _registry_path = path
    return _registry