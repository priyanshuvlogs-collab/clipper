"""Professional clip rendering with FFmpeg.

Produces high-quality 1080p H.264/AAC clips with:
- Aspect conversion (9:16 vertical, 16:9 horizontal, 1:1 square)
- Optional burned-in short-form captions (styled ASS)
- Optional subtle Ken Burns zoom
- Optional background music bed (looped + mixed under speech)
- Text/emoji overlays (drawtext with per-overlay timing)
- AI layers: generated B-roll (image / video) and voiceover / SFX / music
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .media import MediaError, probe

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


def _base_filters(aspect: str, ken_burns: bool, fps: int = 30) -> str:
    """Scale/crop the source to the target frame (+ optional slow push-in)."""
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
    return ",".join(filters)


def _top_filters(ass_path: str | None, overlays: list[dict[str, Any]] | None) -> str:
    """Captions + text overlays; applied last so they sit above any B-roll."""
    filters: list[str] = []
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


def build_video_filters(
    aspect: str,
    ken_burns: bool,
    ass_path: str | None,
    overlays: list[dict[str, Any]] | None,
    fps: int = 30,
) -> str:
    return f"{_base_filters(aspect, ken_burns, fps)},{_top_filters(ass_path, overlays)}"


_AFMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


def _has_audio(path: str) -> bool:
    try:
        return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))
    except MediaError:
        return False


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
    layers: list[dict[str, Any]] | None = None,
    original_volume: float = 1.0,
    fps: int = 30,
) -> Path:
    """Render one clip.

    ``layers`` are AI-generated media placed on the clip's own timeline:
    ``{kind, path, start, end, volume}`` with kind ``image`` / ``video``
    (full-frame B-roll under the captions) or ``voiceover`` / ``sfx`` /
    ``music`` (mixed with the original audio, scaled by ``original_volume``).
    """
    duration = max(0.2, end - start)
    w, h = ASPECT_RESOLUTIONS.get(aspect, ASPECT_RESOLUTIONS["9:16"])

    layers = [dict(l) for l in (layers or [])]
    if music_path:
        layers.append({"kind": "music", "path": music_path, "start": 0.0, "end": duration, "volume": music_volume})

    cmd: list[str] = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", source_path,
    ]
    graph: list[str] = [f"[0:v]{_base_filters(aspect, ken_burns, fps)}[v0]"]
    n_inputs = 1
    vlabel = "v0"

    # Audio bed: the source's own track, or silence if it has none.
    if _has_audio(source_path):
        graph.append(f"[0:a]{_AFMT},volume={max(0.0, original_volume):.3f}[a0]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        graph.append(f"[{n_inputs}:a]{_AFMT}[a0]")
        n_inputs += 1
    alabels = ["a0"]

    for layer in layers:
        kind = layer.get("kind")
        path = str(layer.get("path") or "")
        ls = max(0.0, min(float(layer.get("start") or 0.0), duration))
        le = max(ls, min(float(layer.get("end") or duration), duration))
        length = le - ls
        if not path or length < 0.1:
            continue
        idx = n_inputs

        if kind in ("image", "video"):
            if kind == "image":
                cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{length:.3f}", "-i", path]
                chain = (
                    f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                    f"zoompan=z='min(pzoom+0.0008,1.15)':d=1:"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
                )
            else:
                cmd += ["-t", f"{length:.3f}", "-i", path]
                chain = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
            chain += ",format=yuva420p"
            if length >= 1.0:  # quick cross-fade in/out
                chain += f",fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st={length - 0.2:.3f}:d=0.2:alpha=1"
            chain += f",setpts=PTS-STARTPTS+{ls:.3f}/TB"
            graph.append(f"[{idx}:v]{chain}[b{idx}]")
            graph.append(
                f"[{vlabel}][b{idx}]overlay=eof_action=pass:"
                f"enable='between(t,{ls:.3f},{le:.3f})'[v{idx}]"
            )
            vlabel = f"v{idx}"
        elif kind in ("voiceover", "sfx", "music"):
            if kind == "music":
                cmd += ["-stream_loop", "-1", "-i", path]
            else:
                cmd += ["-i", path]
            vol = max(0.0, float(layer.get("volume", 1.0)))
            chain = f"{_AFMT},atrim=0:{length:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f}"
            if kind == "music" and length > 2.0:
                chain += f",afade=t=in:st=0:d=0.5,afade=t=out:st={length - 1.0:.3f}:d=1.0"
            chain += f",adelay={int(ls * 1000)}:all=1"
            graph.append(f"[{idx}:a]{chain}[a{idx}]")
            alabels.append(f"a{idx}")
        else:
            continue
        n_inputs += 1

    graph.append(f"[{vlabel}]{_top_filters(ass_path, overlays)}[vout]")
    if len(alabels) > 1:
        graph.append(
            "".join(f"[{l}]" for l in alabels)
            + f"amix=inputs={len(alabels)}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
    else:
        graph.append("[a0]anull[aout]")

    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]

    # stderr goes to a temp file: reading it only after stdout could deadlock
    # on a full pipe for long error output.
    with tempfile.TemporaryFile(mode="w+") as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, text=True)
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
            errf.seek(0)
            raise MediaError(f"ffmpeg render failed: {errf.read().strip()[-2000:]}")
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
