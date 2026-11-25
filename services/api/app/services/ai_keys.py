"""API-key resolution for the AI providers.

A key saved from the Settings page (``<data_dir>/ai_keys.json``, mode 0600)
wins over the environment / .env value. Keys are never returned by the API —
only a "…last4" hint.
"""

from __future__ import annotations

import json
import os
import threading

from ..config import settings

_lock = threading.Lock()
PROVIDERS = ("xai", "elevenlabs", "anthropic")
NAMES = {"xai": "xAI (Grok)", "elevenlabs": "ElevenLabs", "anthropic": "Anthropic (Claude)"}


class AiError(RuntimeError):
    """A provider call failed or is not configured (message is user-facing)."""


def _load() -> dict[str, str]:
    try:
        data = json.loads(settings.ai_keys_file.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if k in PROVIDERS and v}
    except (OSError, ValueError):
        return {}


def get_key(provider: str) -> str:
    saved = _load().get(provider, "")
    return saved or getattr(settings, f"{provider}_api_key", "")


def require_key(provider: str) -> str:
    key = get_key(provider)
    if not key:
        raise AiError(f"No {NAMES.get(provider, provider)} API key configured — add one on the Settings page.")
    return key


def save_keys(updates: dict[str, str | None]) -> None:
    """Persist keys; ``""`` removes a saved key, ``None`` leaves it untouched."""
    with _lock:
        data = _load()
        for provider, value in updates.items():
            if provider not in PROVIDERS or value is None:
                continue
            value = value.strip()
            if value:
                data[provider] = value
            else:
                data.pop(provider, None)
        path = settings.ai_keys_file
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.chmod(path, 0o600)


def hint(provider: str) -> str:
    key = get_key(provider)
    return f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else "")


def source(provider: str) -> str:
    if _load().get(provider):
        return "saved"
    return "env" if getattr(settings, f"{provider}_api_key", "") else ""
