"""Professional clip rendering with FFmpeg.

Produces high-quality 1080p H.264/AAC clips with:
- Aspect conversion (9:16 vertical, 16:9 horizontal, 1:1 square)
- Optional burned-in short-form captions (styled ASS)
- Optional subtle Ken Burns zoom
- Optional background music bed (looped + mixed under speech)
- Text/emoji overlays (drawtext with per-overlay timing)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from .media import MediaError

ASPECT_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}


def _escape_filter_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument."""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
        .replace("%", "\\%")
        .replace(";", "\\;")
    )


def build_video_filters(
    aspect: str,
    ken_burns: bool,
    ass_path: str | None,
    overlays: list[dict[str, Any]] | None,
    fps: int = 30,
) -> str:
    w, h = ASPECT_RESOLUTIONS.get(aspect, ASPECT_RESOLUTIONS["9:16"])
    filters: list[str] = [
        f"scale={w}:{h}:force_original_aspect_ratio=increase",
        f"crop={w}:{h}",
        f"fps={fps}",
    ]
    if ken_burns:
        # Subtle continuous push-in; pzoom carries zoom across frames (d=1).
        filters.append(
            f"zoompan=z='min(pzoom+0.0004,1.10)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
        )
    if ass_path:
        filters.append(f"ass='{_escape_filter_path(ass_path)}'")
    for ov in overlays or []:
        text = _escape_drawtext(str(ov.get("text", "")).strip())
        if not text:
            continue
        size = int(ov.get("size", 56))
        color = str(ov.get("color", "white"))
        x_pct = float(ov.get("x", 50)) / 100.0
        y_pct = float(ov.get("y", 20)) / 100.0
        start = float(ov.get("start", 0.0))
        end = float(ov.get("end", 3.0))
        filters.append(
            "drawtext=font='DejaVu Sans':"
            f"text='{text}':fontsize={size}:fontcolor={color}:"
            "borderw=3:bordercolor=black@0.85:"
            f"x=(w-text_w)*{x_pct:.4f}:y=(h-text_h)*{y_pct:.4f}:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    filters.append("format=yuv420p")
    return ",".join(filters)


def render_clip(
    source_path: str,
    output_path: str,
    start: float,
    end: float,
    aspect: str = "9:16",
    ass_path: str | None = None,
    ken_burns: bool = True,
    music_path: str | None = None,
    music_volume: float = 0.12,
    overlays: list[dict[str, Any]] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    duration = max(0.2, end - start)
    vf = build_video_filters(aspect, ken_burns, ass_path, overlays)

    cmd: list[str] = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", source_path,
    ]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", music_path]
        cmd += [
            "-filter_complex",
            f"[0:v]{vf}[vout];"
            f"[1:a]volume={music_volume:.3f}[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "[vout]", "-map", "[aout]",
        ]
    else:
        cmd += ["-vf", vf, "-map", "0:v:0", "-map", "0:a:0?"]

    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_ms=") and on_progress:
            try:
                done = int(line.split("=", 1)[1]) / 1_000_000.0
                on_progress(min(99.0, done / duration * 100.0))
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        err = (proc.stderr.read() if proc.stderr else "").strip()[-2000:]
        raise MediaError(f"ffmpeg render failed: {err}")
    if on_progress:
        on_progress(100.0)
    return Path(output_path)


def concat_clips(clip_paths: list[str], output_path: str) -> Path:
    """Merge already-rendered clips (uniform codecs) with the concat demuxer."""
    list_file = Path(output_path).with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{p}'" for p in clip_paths) + "\n", encoding="utf-8"
    )
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", "-movflags", "+faststart",
                output_path,
            ],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            # Codec mismatch — fall back to re-encoding.
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "concat", "-safe", "0", "-i", str(list_file),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    output_path,
                ],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise MediaError(f"ffmpeg concat failed: {proc.stderr.strip()[-2000:]}")
    finally:
        list_file.unlink(missing_ok=True)
    return Path(output_path)
