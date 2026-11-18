"""ElevenLabs client: voiceover (TTS), sound effects, music, voices, credits."""

from __future__ import annotations

from typing import Any

import requests

from ..config import settings
from .ai_keys import AiError, require_key

OUTPUT_FORMAT = "mp3_44100_128"


def _url(path: str) -> str:
    return f"{settings.elevenlabs_base_url.rstrip('/')}{path}"


def _request(method: str, path: str, what: str, **kwargs) -> requests.Response:
    headers = {"xi-api-key": require_key("elevenlabs")}
    try:
        resp = requests.request(method, _url(path), headers=headers, **kwargs)
    except requests.RequestException as exc:
        raise AiError(f"Could not reach ElevenLabs for {what}: {exc}") from exc
    if resp.status_code >= 400:
        try:
            detail: Any = resp.json().get("detail", resp.text[:300])
            if isinstance(detail, dict):
                detail = detail.get("message", detail)
        except ValueError:
            detail = resp.text[:300]
        raise AiError(f"ElevenLabs {what} failed ({resp.status_code}): {detail}")
    return resp


def text_to_speech(text: str, voice_id: str | None = None) -> bytes:
    voice = voice_id or settings.elevenlabs_voice_id
    resp = _request(
        "POST", f"/v1/text-to-speech/{voice}", "voiceover",
        params={"output_format": OUTPUT_FORMAT},
        json={"text": text, "model_id": settings.elevenlabs_tts_model},
        timeout=300,
    )
    return resp.content


def sound_effect(prompt: str, duration: float | None = None) -> bytes:
    body: dict[str, Any] = {"text": prompt}
    if duration:
        body["duration_seconds"] = round(max(0.5, min(30.0, duration)), 1)
    resp = _request(
        "POST", "/v1/sound-generation", "sound effect",
        params={"output_format": OUTPUT_FORMAT}, json=body, timeout=300,
    )
    return resp.content


def music(prompt: str, duration: float = 30.0) -> bytes:
    resp = _request(
        "POST", "/v1/music", "music",
        params={"output_format": OUTPUT_FORMAT},
        json={"prompt": prompt, "music_length_ms": int(max(10.0, min(300.0, duration)) * 1000)},
        timeout=600,
    )
    return resp.content


def list_voices() -> list[dict[str, Any]]:
    data = _request("GET", "/v2/voices", "voice list", params={"page_size": 100}, timeout=60).json()
    out = []
    for v in data.get("voices", []):
        labels = v.get("labels") or {}
        out.append({
            "voice_id": v.get("voice_id", ""),
            "name": v.get("name", ""),
            "description": ", ".join(str(x) for x in labels.values() if x)[:80],
            "preview_url": v.get("preview_url") or "",
        })
    return out


def credits() -> dict[str, Any]:
    """Live character-credit balance for the configured key."""
    data = _request("GET", "/v1/user/subscription", "credits", timeout=30).json()
    used = int(data.get("character_count") or 0)
    limit = int(data.get("character_limit") or 0)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "tier": data.get("tier", "")}
