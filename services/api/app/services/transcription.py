"""Transcription engine with automatic fallback discovery.

Primary engine is Faster-Whisper running locally. If the local model is
unavailable, fails, or has been measured to be very slow on this machine,
remote engines are tried automatically in order of preference:

    Groq Whisper -> Deepgram -> AssemblyAI

Remote engines only participate when their API key is configured, so the
"auto discovery" is simply: probe what's usable, then walk the chain.

All engines normalise to the same result shape::

    {
        "engine": str,
        "language": str,
        "language_probability": float,
        "text": str,
        "segments": [{"start", "end", "text", "words": [{"start", "end", "word"}]}],
    }
"""

from __future__ import annotations

import importlib.util
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

from ..config import settings

log = logging.getLogger("proclipper.transcription")

ProgressFn = Callable[[float], None]


class TranscriptionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Engine discovery
# ---------------------------------------------------------------------------

_local_slow_flag = False  # set when a local run exceeded the slowness threshold


def discover_engines() -> list[dict[str, Any]]:
    """Report which engines are usable right now (drives UI + fallback chain)."""
    local_available = importlib.util.find_spec("faster_whisper") is not None
    local_detail = f"model={settings.whisper_model}"
    if _local_slow_flag:
        local_detail += " (measured slow on this machine — remote engines recommended)"
    return [
        {
            "id": "local",
            "name": f"Faster-Whisper ({settings.whisper_model})",
            "kind": "local",
            "available": local_available,
            "detail": local_detail if local_available else "faster-whisper not installed",
        },
        {
            "id": "groq",
            "name": "Groq Whisper (whisper-large-v3)",
            "kind": "remote",
            "available": bool(settings.groq_api_key),
            "detail": "free tier — set GROQ_API_KEY" if not settings.groq_api_key else "ready",
        },
        {
            "id": "deepgram",
            "name": "Deepgram Nova-2",
            "kind": "remote",
            "available": bool(settings.deepgram_api_key),
            "detail": "free tier — set DEEPGRAM_API_KEY" if not settings.deepgram_api_key else "ready",
        },
        {
            "id": "assemblyai",
            "name": "AssemblyAI",
            "kind": "remote",
            "available": bool(settings.assemblyai_api_key),
            "detail": "free tier — set ASSEMBLYAI_API_KEY" if not settings.assemblyai_api_key else "ready",
        },
    ]


def _engine_chain(preferred: str) -> list[str]:
    engines = {e["id"]: e for e in discover_engines()}
    order: list[str]
    if preferred != "auto" and preferred in engines:
        order = [preferred] + [e for e in ("local", "groq", "deepgram", "assemblyai") if e != preferred]
    elif _local_slow_flag:
        # Local proved slow: prefer remote engines first when any is configured.
        order = ["groq", "deepgram", "assemblyai", "local"]
    else:
        order = ["local", "groq", "deepgram", "assemblyai"]
    return [e for e in order if engines[e]["available"]]


# ---------------------------------------------------------------------------
# Local Faster-Whisper
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_model_cache: dict[str, Any] = {}


def _get_local_model():
    from faster_whisper import WhisperModel

    key = f"{settings.whisper_model}:{settings.whisper_device}:{settings.whisper_compute_type}"
    with _model_lock:
        if key not in _model_cache:
            log.info("loading faster-whisper model %s", key)
            _model_cache[key] = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        return _model_cache[key]


def _transcribe_local(audio_path: str, language: str, on_progress: ProgressFn) -> dict[str, Any]:
    global _local_slow_flag
    model = _get_local_model()
    started = time.monotonic()

    seg_iter, info = model.transcribe(
        audio_path,
        language=None if language in ("", "auto") else language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    total = float(info.duration or 0) or 1.0

    segments: list[dict[str, Any]] = []
    for seg in seg_iter:
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
            for w in (seg.words or [])
        ]
        segments.append(
            {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words}
        )
        on_progress(min(99.0, seg.end / total * 100.0))

    elapsed = time.monotonic() - started
    minutes = total / 60.0
    if minutes >= 0.5 and elapsed / minutes > settings.whisper_slow_threshold:
        _local_slow_flag = True
        log.warning(
            "local whisper is slow (%.0fs per audio-minute) — remote engines will be preferred",
            elapsed / minutes,
        )

    return {
        "engine": "local",
        "language": info.language or language or "en",
        "language_probability": float(info.language_probability or 0.0),
        "text": " ".join(s["text"] for s in segments).strip(),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Groq (OpenAI-compatible Whisper endpoint)
# ---------------------------------------------------------------------------

def _transcribe_groq(audio_path: str, language: str, on_progress: ProgressFn) -> dict[str, Any]:
    on_progress(5.0)
    data: dict[str, Any] = {
        "model": "whisper-large-v3",
        "response_format": "verbose_json",
        "timestamp_granularities[]": ["segment", "word"],
    }
    if language not in ("", "auto"):
        data["language"] = language
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            data=data,
            files={"file": (Path(audio_path).name, f, "audio/wav")},
            timeout=600,
        )
    if resp.status_code != 200:
        raise TranscriptionError(f"Groq error {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    on_progress(90.0)

    words = [
        {"start": float(w.get("start", 0)), "end": float(w.get("end", 0)), "word": w.get("word", "")}
        for w in body.get("words", [])
    ]
    segments = []
    for seg in body.get("segments", []):
        s, e = float(seg.get("start", 0)), float(seg.get("end", 0))
        segments.append(
            {
                "start": s,
                "end": e,
                "text": (seg.get("text") or "").strip(),
                "words": [w for w in words if s - 0.05 <= w["start"] < e + 0.05],
            }
        )
    return {
        "engine": "groq",
        "language": body.get("language") or language or "en",
        "language_probability": 1.0,
        "text": (body.get("text") or "").strip(),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Deepgram
# ---------------------------------------------------------------------------

def _transcribe_deepgram(audio_path: str, language: str, on_progress: ProgressFn) -> dict[str, Any]:
    on_progress(5.0)
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
    }
    if language not in ("", "auto"):
        params["language"] = language
    else:
        params["detect_language"] = "true"
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers={"Authorization": f"Token {settings.deepgram_api_key}", "Content-Type": "audio/wav"},
            data=f,
            timeout=600,
        )
    if resp.status_code != 200:
        raise TranscriptionError(f"Deepgram error {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    on_progress(90.0)

    channel = body.get("results", {}).get("channels", [{}])[0]
    alt = channel.get("alternatives", [{}])[0]
    detected = channel.get("detected_language") or language or "en"

    segments = []
    for utt in body.get("results", {}).get("utterances", []) or []:
        segments.append(
            {
                "start": float(utt.get("start", 0)),
                "end": float(utt.get("end", 0)),
                "text": (utt.get("transcript") or "").strip(),
                "words": [
                    {"start": float(w.get("start", 0)), "end": float(w.get("end", 0)),
                     "word": w.get("punctuated_word") or w.get("word", "")}
                    for w in utt.get("words", [])
                ],
            }
        )
    if not segments and alt.get("words"):
        # Fall back to one segment built from words.
        words = [
            {"start": float(w.get("start", 0)), "end": float(w.get("end", 0)),
             "word": w.get("punctuated_word") or w.get("word", "")}
            for w in alt["words"]
        ]
        segments = [{"start": words[0]["start"], "end": words[-1]["end"],
                     "text": alt.get("transcript", ""), "words": words}]

    return {
        "engine": "deepgram",
        "language": detected,
        "language_probability": 1.0,
        "text": (alt.get("transcript") or "").strip(),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# AssemblyAI
# ---------------------------------------------------------------------------

def _transcribe_assemblyai(audio_path: str, language: str, on_progress: ProgressFn) -> dict[str, Any]:
    headers = {"authorization": settings.assemblyai_api_key}
    on_progress(2.0)
    with open(audio_path, "rb") as f:
        up = requests.post("https://api.assemblyai.com/v2/upload", headers=headers, data=f, timeout=600)
    if up.status_code != 200:
        raise TranscriptionError(f"AssemblyAI upload error {up.status_code}: {up.text[:400]}")
    upload_url = up.json()["upload_url"]
    on_progress(20.0)

    payload: dict[str, Any] = {"audio_url": upload_url, "punctuate": True, "format_text": True}
    if language not in ("", "auto"):
        payload["language_code"] = language
    else:
        payload["language_detection"] = True
    tr = requests.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=payload, timeout=60)
    if tr.status_code != 200:
        raise TranscriptionError(f"AssemblyAI error {tr.status_code}: {tr.text[:400]}")
    tid = tr.json()["id"]

    while True:
        time.sleep(3)
        poll = requests.get(f"https://api.assemblyai.com/v2/transcript/{tid}", headers=headers, timeout=60).json()
        status = poll.get("status")
        if status == "completed":
            break
        if status == "error":
            raise TranscriptionError(f"AssemblyAI failed: {poll.get('error')}")
        on_progress(min(85.0, 20.0 + (time.monotonic() % 60)))

    words = [
        {"start": w["start"] / 1000.0, "end": w["end"] / 1000.0, "word": w["text"]}
        for w in poll.get("words", []) or []
    ]
    # Build ~sentence segments from words using punctuation boundaries.
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for w in words:
        current.append(w)
        if w["word"].rstrip().endswith((".", "?", "!", "।")) or (current[-1]["end"] - current[0]["start"]) > 12:
            segments.append(
                {"start": current[0]["start"], "end": current[-1]["end"],
                 "text": " ".join(x["word"] for x in current), "words": current}
            )
            current = []
    if current:
        segments.append(
            {"start": current[0]["start"], "end": current[-1]["end"],
             "text": " ".join(x["word"] for x in current), "words": current}
        )

    return {
        "engine": "assemblyai",
        "language": poll.get("language_code") or language or "en",
        "language_probability": float(poll.get("language_confidence") or 1.0),
        "text": poll.get("text") or "",
        "segments": segments,
    }


_ENGINES: dict[str, Callable[[str, str, ProgressFn], dict[str, Any]]] = {
    "local": _transcribe_local,
    "groq": _transcribe_groq,
    "deepgram": _transcribe_deepgram,
    "assemblyai": _transcribe_assemblyai,
}


def transcribe(
    audio_path: str,
    language: str = "auto",
    preferred_engine: str = "auto",
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Transcribe with automatic fallback across all available engines."""
    progress = on_progress or (lambda _p: None)
    chain = _engine_chain(preferred_engine)
    if not chain:
        raise TranscriptionError(
            "No transcription engine is available. Install faster-whisper or set "
            "GROQ_API_KEY / DEEPGRAM_API_KEY / ASSEMBLYAI_API_KEY."
        )

    errors: list[str] = []
    for engine_id in chain:
        try:
            log.info("transcribing with engine=%s language=%s", engine_id, language)
            result = _ENGINES[engine_id](audio_path, language, progress)
            progress(100.0)
            return result
        except Exception as exc:  # noqa: BLE001 — fall through the chain
            log.warning("engine %s failed: %s", engine_id, exc)
            errors.append(f"{engine_id}: {exc}")

    raise TranscriptionError("All transcription engines failed — " + json.dumps(errors))
