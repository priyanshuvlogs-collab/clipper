"""Subtitle generation: SRT, VTT, plain text, and styled ASS for burn-in."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt_srt(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    ms = round((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def _fmt_vtt(t: float) -> str:
    return _fmt_srt(t).replace(",", ".")


def _fmt_ass(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    cs = round((s - int(s)) * 100)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def write_srt(segments: list[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines += [str(i), f"{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}", seg["text"].strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_vtt(segments: list[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines += [f"{_fmt_vtt(seg['start'])} --> {_fmt_vtt(seg['end'])}", seg["text"].strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_txt(text: str, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def slice_segments(segments: list[dict[str, Any]], start: float, end: float, rebase: bool = True) -> list[dict[str, Any]]:
    """Return segments overlapping [start, end], clamped (and rebased to t=0)."""
    out: list[dict[str, Any]] = []
    offset = start if rebase else 0.0
    for seg in segments:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        words = [
            {"start": max(seg["start"], max(start, w["start"])) - offset,
             "end": min(end, w["end"]) - offset,
             "word": w["word"]}
            for w in seg.get("words", [])
            if w["end"] > start and w["start"] < end
        ]
        out.append(
            {
                "start": max(0.0, max(start, seg["start"]) - offset),
                "end": min(end, seg["end"]) - offset,
                "text": seg["text"].strip(),
                "words": words,
            }
        )
    return out


def build_caption_chunks(segments: list[dict[str, Any]], max_words: int = 3) -> list[dict[str, Any]]:
    """Short-form style captions: small word groups with tight timing.

    Uses word-level timestamps when available; otherwise splits segment text
    evenly across its duration.
    """
    chunks: list[dict[str, Any]] = []
    for seg in segments:
        words = seg.get("words") or []
        if words:
            for i in range(0, len(words), max_words):
                group = words[i : i + max_words]
                text = "".join(w["word"] for w in group).strip() or " ".join(w["word"].strip() for w in group)
                chunks.append({"start": group[0]["start"], "end": group[-1]["end"], "text": text})
        else:
            tokens = seg["text"].split()
            if not tokens:
                continue
            dur = max(0.2, seg["end"] - seg["start"])
            n = max(1, (len(tokens) + max_words - 1) // max_words)
            step = dur / n
            for i in range(n):
                group = tokens[i * max_words : (i + 1) * max_words]
                chunks.append(
                    {"start": seg["start"] + i * step, "end": seg["start"] + (i + 1) * step,
                     "text": " ".join(group)}
                )
    # Guarantee monotonic, non-zero-length cues.
    for c in chunks:
        if c["end"] - c["start"] < 0.08:
            c["end"] = c["start"] + 0.08
    return chunks


DEFAULT_CAPTION_STYLE = {
    "font": "DejaVu Sans",
    "size": 64,
    "primary_color": "&H00FFFFFF",   # white
    "highlight_color": "&H0000E5FF", # yellow-ish (ASS is BGR)
    "outline_color": "&H00000000",
    "outline": 4,
    "margin_v": 460,                  # distance from bottom (script is 1080x1920)
    "bold": -1,
}


def write_ass(
    segments: list[dict[str, Any]],
    path: str | Path,
    play_res: tuple[int, int] = (1080, 1920),
    style: dict[str, Any] | None = None,
    max_words: int = 3,
) -> Path:
    """Write a styled ASS subtitle file for burn-in (short-form caption look)."""
    st = {**DEFAULT_CAPTION_STYLE, **(style or {})}
    w, h = play_res
    chunks = build_caption_chunks(segments, max_words=max_words)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{st['font']},{st['size']},{st['primary_color']},{st['highlight_color']},{st['outline_color']},&H96000000,{st['bold']},0,0,0,100,100,0,0,1,{st['outline']},2,2,60,60,{st['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for c in chunks:
        text = c["text"].replace("\n", " ").replace("{", "(").replace("}", ")").upper()
        pop = r"{\fad(60,40)\fscx108\fscy108\t(0,90,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{_fmt_ass(c['start'])},{_fmt_ass(c['end'])},Caption,,0,0,0,,{pop}{text}")

    path = Path(path)
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path
