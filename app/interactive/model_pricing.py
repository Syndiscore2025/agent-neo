"""
Model pricing + discovery cache.

Prices come from the community LiteLLM pricing file with a bundled fallback
table, so the picker always has data even offline. Provider model lists are
discovered live via the Anthropic/OpenAI /v1/models APIs. A background loop
started in app.main refreshes the cache on an interval (in-process "cron").
"""

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRICING_SOURCE_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# Bundled fallback (USD per million tokens) — used when no cache exists yet.
FALLBACK_PRICING: dict[str, dict] = {
    "claude-sonnet-4-6": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    "claude-opus-4-8": {"input_per_mtok": 5.0, "output_per_mtok": 25.0},
    "gpt-4o": {"input_per_mtok": 2.5, "output_per_mtok": 10.0},
    "o1": {"input_per_mtok": 15.0, "output_per_mtok": 60.0},
    "o3": {"input_per_mtok": 2.0, "output_per_mtok": 8.0},
}

_DATE_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_OPENAI_INCLUDE_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")
_OPENAI_EXCLUDE_TOKENS = (
    "audio", "realtime", "tts", "whisper", "embedding", "dall-e",
    "moderation", "transcribe", "search", "image", "instruct", "codex",
)
_MAX_DISCOVERED_PER_PROVIDER = 25

# In-memory cache: {"updated_at": iso, "pricing": {...}, "models": {...}}
_cache: Optional[dict] = None


def _cache_path() -> Path:
    override = os.getenv("NEO_PRICING_CACHE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".agent-neo" / "model_pricing.json"


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_cache_path().read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def get_pricing(api_model: str) -> Optional[dict]:
    """Pricing for a concrete API model id: {input_per_mtok, output_per_mtok}."""
    if not api_model:
        return None
    cached = _load_cache().get("pricing", {}).get(api_model)
    return cached or FALLBACK_PRICING.get(api_model)


def get_discovered_models(provider: str) -> list[dict]:
    """Cached provider model list: [{id, label}]. Empty until first refresh."""
    return _load_cache().get("models", {}).get(provider, [])


def last_updated() -> Optional[str]:
    return _load_cache().get("updated_at")


def _parse_litellm_pricing(data: dict) -> dict:
    """Extract anthropic/openai prices (per MTok) from the LiteLLM file."""
    out: dict[str, dict] = {}
    for key, info in data.items():
        if not isinstance(info, dict):
            continue
        if info.get("litellm_provider") not in ("anthropic", "openai"):
            continue
        inp = info.get("input_cost_per_token")
        outp = info.get("output_cost_per_token")
        if not inp and not outp:
            continue
        mid = key.split("/")[-1]
        out[mid] = {
            "input_per_mtok": round((inp or 0) * 1_000_000, 4),
            "output_per_mtok": round((outp or 0) * 1_000_000, 4),
        }
    return out


def _parse_openai_models(data: dict) -> list[dict]:
    """Filter the OpenAI /v1/models list to chat-capable, undated ids."""
    models = []
    for item in data.get("data", []):
        mid = item.get("id", "")
        low = mid.lower()
        if not low.startswith(_OPENAI_INCLUDE_PREFIXES):
            continue
        if any(tok in low for tok in _OPENAI_EXCLUDE_TOKENS):
            continue
        if _DATE_SUFFIX.search(mid):
            continue
        models.append({"id": mid, "label": mid})
    return sorted(models, key=lambda m: m["id"])[:_MAX_DISCOVERED_PER_PROVIDER]


def _parse_anthropic_models(data: dict) -> list[dict]:
    """Filter the Anthropic /v1/models list to claude ids."""
    models = []
    for item in data.get("data", []):
        mid = item.get("id", "")
        if mid.lower().startswith("claude"):
            models.append({"id": mid, "label": item.get("display_name") or mid})
    return sorted(models, key=lambda m: m["id"])[:_MAX_DISCOVERED_PER_PROVIDER]


def _http_get_json(url: str, headers: Optional[dict] = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_model_data() -> bool:
    """
    Fetch pricing + provider model lists and persist the cache.

    Each source is best-effort and independent; returns True if at least one
    source refreshed successfully.
    """
    global _cache
    data = dict(_load_cache())
    ok = False

    try:
        data["pricing"] = _parse_litellm_pricing(_http_get_json(PRICING_SOURCE_URL))
        ok = True
    except Exception as e:
        logger.warning(f"Pricing refresh failed: {e}")

    models = dict(data.get("models", {}))
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            models["anthropic"] = _parse_anthropic_models(_http_get_json(
                "https://api.anthropic.com/v1/models?limit=100",
                {"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
            ))
            ok = True
        except Exception as e:
            logger.warning(f"Anthropic model discovery failed: {e}")
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            models["openai"] = _parse_openai_models(_http_get_json(
                "https://api.openai.com/v1/models",
                {"Authorization": f"Bearer {openai_key}"},
            ))
            ok = True
        except Exception as e:
            logger.warning(f"OpenAI model discovery failed: {e}")
    data["models"] = models

    if ok:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            path = _cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Pricing cache write failed: {e}")
        _cache = data
    return ok


def _is_stale(hours: float) -> bool:
    """True when the cache has never refreshed or is older than the interval."""
    ts = last_updated()
    if not ts:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
        return age.total_seconds() >= hours * 3600
    except Exception:
        return True


async def refresh_loop():
    """
    In-process scheduler: refresh model/pricing data every
    NEO_MODEL_REFRESH_HOURS (default 24; 0 disables).

    The short initial sleep lets short-lived startups (tests, health checks)
    cancel the task before any network call begins.
    """
    import asyncio

    try:
        hours = float(os.getenv("NEO_MODEL_REFRESH_HOURS", "24") or 0)
    except ValueError:
        hours = 24.0
    if hours <= 0:
        return
    await asyncio.sleep(5)
    while True:
        if _is_stale(hours):
            await asyncio.to_thread(refresh_model_data)
        await asyncio.sleep(hours * 3600)
