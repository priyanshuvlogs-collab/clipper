"""FFmpeg / ffprobe helpers shared across the pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise MediaError(f"Command failed ({cmd[0]}): {tail}")
    return proc


def probe(path: str | Path) -> dict:
    proc = run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ]
    )
    return json.loads(proc.stdout)


def probe_video(path: str | Path) -> tuple[float, int, int]:
    """Return (duration_seconds, width, height)."""
    info = probe(path)
    duration = float(info.get("format", {}).get("duration") or 0.0)
    width = height = 0
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            break
    return duration, width, height


def extract_audio(video_path: str | Path, out_path: str | Path, sample_rate: int = 16000) -> Path:
    """Extract mono WAV audio suitable for Whisper and energy analysis."""
    out_path = Path(out_path)
    run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            str(out_path),
        ]
    )
    return out_path


def detect_silences(audio_path: str | Path, noise_db: float = -35.0, min_silence: float = 0.6) -> list[tuple[float, float]]:
    """Return [(start, end)] silence intervals using ffmpeg silencedetect."""
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "info", "-i", str(audio_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in proc.stderr.splitlines():
        line = line.strip()
        if "silence_start:" in line:
            try:
                start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                start = None
        elif "silence_end:" in line and start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                silences.append((start, end))
            except (ValueError, IndexError):
                pass
            start = None
    return silences
