"""xAI (Grok) client: JSON chat, image generation, video generation.

Uses the OpenAI-compatible REST API at ``XAI_BASE_URL``. Model ids are
configurable (``XAI_TEXT_MODEL`` / ``XAI_IMAGE_MODEL`` / ``XAI_VIDEO_MODEL``)
because xAI renames them between releases.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import requests

from ..config import settings
from .ai_keys import AiError, require_key

ASPECTS = {"9:16", "16:9", "1:1"}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {require_key('xai')}", "Content-Type": "application/json"}


def _check(resp: requests.Response, what: str) -> dict[str, Any]:
    if resp.status_code >= 400:
        try:
            body = resp.json()
            err = body.get("error", body)
            detail = err.get("message", err) if isinstance(err, dict) else err
        except ValueError:
            detail = resp.text[:300]
        raise AiError(f"xAI {what} failed ({resp.status_code}): {detail}")
    try:
        return resp.json()
    except ValueError as exc:
        raise AiError(f"xAI {what} returned a non-JSON response") from exc


def _request(method: str, path: str, what: str, **kwargs) -> dict[str, Any]:
    try:
        resp = requests.request(
            method, f"{settings.xai_base_url.rstrip('/')}{path}", headers=_headers(), **kwargs
        )
    except requests.RequestException as exc:
        raise AiError(f"Could not reach xAI for {what}: {exc}") from exc
    return _check(resp, what)


def _download(url: str, what: str) -> bytes:
    try:
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AiError(f"Could not download generated {what}: {exc}") from exc
    return resp.content


def chat_json(system: str, user: str) -> dict[str, Any]:
    """Ask Grok for a JSON object and parse it."""
    data = _request(
        "POST", "/chat/completions", "chat",
        json={
            "model": settings.xai_text_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        },
        timeout=180,
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiError("xAI chat returned an unexpected response shape") from exc
    text = (content or "").strip()
    if text.startswith("```"):  # tolerate fenced output
        text = text.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise AiError("Grok did not return valid JSON for the edit plan") from exc
    if not isinstance(parsed, dict):
        raise AiError("Grok returned JSON that is not an object")
    return parsed


def generate_image(prompt: str, aspect: str = "9:16") -> bytes:
    """Generate one image; returns encoded image bytes (JPEG/PNG)."""
    payload: dict[str, Any] = {
        "model": settings.xai_image_model,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
    }
    if aspect in ASPECTS:
        payload["aspect_ratio"] = aspect
    data = _request("POST", "/images/generations", "image generation", json=payload, timeout=300)
    try:
        item = data["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiError("xAI image generation returned no image") from exc
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return _download(item["url"], "image")
    raise AiError("xAI image generation returned no image data")


def generate_video(prompt: str, duration: float = 6.0, aspect: str = "9:16", timeout: float = 900.0) -> bytes:
    """Start a video generation, poll until it finishes, return the MP4 bytes."""
    payload: dict[str, Any] = {
        "model": settings.xai_video_model,
        "prompt": prompt,
        "duration": int(max(1, min(15, round(duration)))),
        "resolution": settings.xai_video_resolution,
    }
    if aspect in ASPECTS:
        payload["aspect_ratio"] = aspect
    started = _request("POST", "/videos/generations", "video generation", json=payload, timeout=120)
    request_id = started.get("request_id") or started.get("id")
    if not request_id:
        raise AiError("xAI video generation did not return a request id")

    deadline = time.monotonic() + timeout
    delay = 4.0
    while time.monotonic() < deadline:
        time.sleep(delay)
        delay = min(delay * 1.3, 15.0)
        status = _request("GET", f"/videos/{request_id}", "video status", timeout=60)
        video = status.get("video") or {}
        state = str(status.get("status", "")).lower()
        if video.get("url"):
            return _download(video["url"], "video")
        if state in {"failed", "expired", "error", "cancelled"}:
            raise AiError(f"xAI video generation {state}: {status.get('error') or 'no details'}")
    raise AiError("xAI video generation timed out")
