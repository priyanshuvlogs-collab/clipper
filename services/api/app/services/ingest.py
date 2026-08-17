"""Source acquisition: local uploads, YouTube links (yt-dlp) and direct URLs."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

import requests

from ..config import settings

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/|live/|embed/)|youtu\.be/)",
    re.IGNORECASE,
)


class IngestError(RuntimeError):
    pass


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.search(url))


def classify_url(url: str) -> str:
    return "youtube" if is_youtube_url(url) else "url"


def save_upload(job_id: str, filename: str, stream) -> Path:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestError(f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    dest = settings.sources_dir / f"{job_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(stream, out, length=1024 * 1024)
    return dest


def download_youtube(job_id: str, url: str, on_progress: Callable[[float], None] | None = None) -> tuple[Path, str]:
    """Download a YouTube video with yt-dlp. Returns (path, title)."""
    try:
        import yt_dlp  # lazy import: heavy and optional at API boot
    except ImportError as exc:  # pragma: no cover
        raise IngestError("yt-dlp is not installed on the server") from exc

    out_template = str(settings.sources_dir / f"{job_id}.%(ext)s")

    def hook(d: dict) -> None:
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                on_progress(min(99.0, done / total * 100.0))

    opts = {
        "outtmpl": out_template,
        # Prefer <=1080p mp4-compatible streams to keep processing fast.
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title") or url
        path = Path(ydl.prepare_filename(info))
        # merge_output_format may change the extension
        if not path.exists():
            candidates = list(settings.sources_dir.glob(f"{job_id}.*"))
            if not candidates:
                raise IngestError("yt-dlp finished but no output file was found")
            path = candidates[0]
    return path, title


def download_direct(job_id: str, url: str, on_progress: Callable[[float], None] | None = None) -> Path:
    """Download a direct video URL with streaming + progress."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    ext = Path(url.split("?")[0]).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = {
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
        }.get(content_type.split(";")[0].strip(), ".mp4")

    dest = settings.sources_dir / f"{job_id}{ext}"
    total = int(resp.headers.get("content-length") or 0)
    done = 0
    with dest.open("wb") as out:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            out.write(chunk)
            done += len(chunk)
            if on_progress and total:
                on_progress(min(99.0, done / total * 100.0))
    return dest
