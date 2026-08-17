"""Job pipeline: ingest -> probe -> transcribe -> detect clips -> render.

Runs on worker threads (see app.worker); every step persists progress so the
frontend can poll. Each stage owns a share of the job progress bar:

    downloading 0-15 | audio 15-20 | transcribing 20-60 | detecting 60-70 | rendering 70-100
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import settings
from ..database import SessionLocal
from ..models import Clip, Job
from . import clip_detection, ingest, media, rendering, subtitles, transcription

log = logging.getLogger("proclipper.pipeline")


def _update(job_id: str, **fields) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()


def _stage_progress(job_id: str, stage: str, lo: float, hi: float):
    def cb(pct: float) -> None:
        _update(job_id, stage=stage, progress=round(lo + (hi - lo) * pct / 100.0, 1))
    return cb


def process_job(job_id: str) -> None:
    """Full pipeline for a newly created job."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        params = dict(job.params or {})
        source_type, source, video_path = job.source_type, job.source, job.video_path

    try:
        _update(job_id, status="running", stage="downloading", progress=1.0)

        # 1) Acquire source ------------------------------------------------
        if source_type == "youtube":
            path, title = ingest.download_youtube(job_id, source, _stage_progress(job_id, "downloading", 1, 15))
            _update(job_id, video_path=str(path), title=title)
            video_path = str(path)
        elif source_type == "url":
            path = ingest.download_direct(job_id, source, _stage_progress(job_id, "downloading", 1, 15))
            _update(job_id, video_path=str(path))
            video_path = str(path)
        # uploads already have video_path set

        # 2) Probe + extract audio ----------------------------------------
        _update(job_id, stage="probing", progress=15.0)
        duration, width, height = media.probe_video(video_path)
        _update(job_id, duration=duration, width=width, height=height, stage="extracting_audio", progress=16.0)

        audio_path = str(settings.sources_dir / f"{job_id}.wav")
        media.extract_audio(video_path, audio_path)
        _update(job_id, audio_path=audio_path, progress=20.0)

        # 3) Transcribe -----------------------------------------------------
        _update(job_id, stage="transcribing")
        result = transcription.transcribe(
            audio_path,
            language=params.get("language", "auto"),
            preferred_engine=params.get("engine", "auto"),
            on_progress=_stage_progress(job_id, "transcribing", 20, 60),
        )

        job_out = settings.outputs_dir / job_id
        job_out.mkdir(parents=True, exist_ok=True)
        srt = subtitles.write_srt(result["segments"], job_out / "transcript.srt")
        vtt = subtitles.write_vtt(result["segments"], job_out / "transcript.vtt")
        txt = subtitles.write_txt(result["text"], job_out / "transcript.txt")
        _update(
            job_id,
            language=result["language"],
            language_probability=result["language_probability"],
            transcription_engine=result["engine"],
            transcript_text=result["text"],
            segments=result["segments"],
            srt_path=str(srt), vtt_path=str(vtt), txt_path=str(txt),
            stage="detecting", progress=60.0,
        )

        # 4) Detect clips ---------------------------------------------------
        silences = media.detect_silences(audio_path)
        candidates = clip_detection.detect_clips(
            result["segments"],
            audio_path,
            silences,
            num_clips=int(params.get("num_clips", 5)),
            min_duration=float(params.get("min_duration", 15.0)),
            max_duration=float(params.get("max_duration", 60.0)),
            remove_silence=bool(params.get("remove_silence", True)),
        )

        render_settings = {
            "aspect": params.get("aspect", "9:16"),
            "burn_subtitles": bool(params.get("burn_subtitles", True)),
            "ken_burns": bool(params.get("ken_burns", True)),
            "music_path": "",
            "music_volume": float(params.get("music_volume", 0.12)),
        }
        clip_ids: list[str] = []
        with SessionLocal() as db:
            for idx, cand in enumerate(candidates):
                clip = Clip(
                    job_id=job_id,
                    order_index=idx,
                    start=round(cand.start, 3),
                    end=round(min(cand.end, duration or cand.end), 3),
                    title=cand.title,
                    hook_text=cand.hook_text,
                    transcript=cand.text,
                    score=cand.score,
                    score_breakdown=cand.breakdown,
                    render_settings=dict(render_settings),
                )
                db.add(clip)
                db.flush()
                clip_ids.append(clip.id)
            db.commit()
        _update(job_id, stage="rendering" if params.get("auto_render", True) else "completed", progress=70.0)

        # 5) Render ---------------------------------------------------------
        if params.get("auto_render", True) and clip_ids:
            span = 30.0 / len(clip_ids)
            for i, clip_id in enumerate(clip_ids):
                render_clip_task(clip_id)
                _update(job_id, progress=round(70.0 + span * (i + 1), 1))

        _update(job_id, status="completed", stage="completed", progress=100.0)

    except Exception as exc:  # noqa: BLE001 — job-level catch-all, persisted for the UI
        log.exception("job %s failed", job_id)
        _update(job_id, status="failed", stage="failed", error=str(exc)[:2000])


def render_clip_task(clip_id: str) -> None:
    """Render (or re-render) a single clip using its stored settings."""
    with SessionLocal() as db:
        clip = db.get(Clip, clip_id)
        if clip is None:
            return
        job = db.get(Job, clip.job_id)
        if job is None or not job.video_path:
            return
        video_path = job.video_path
        segments = list(job.segments or [])
        rs = dict(clip.render_settings or {})
        overlays = list(clip.overlays or [])
        start, end = clip.start, clip.end
        job_id = clip.job_id

    def prog(p: float) -> None:
        with SessionLocal() as db:
            c = db.get(Clip, clip_id)
            if c is not None:
                c.render_progress = round(p, 1)
                db.commit()

    try:
        with SessionLocal() as db:
            c = db.get(Clip, clip_id)
            c.render_status = "rendering"
            c.render_progress = 0.0
            c.render_error = ""
            db.commit()

        out_dir = settings.outputs_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"clip_{clip_id}.mp4"

        # Per-clip subtitle assets (always produced, even without burn-in).
        local_segments = subtitles.slice_segments(segments, start, end, rebase=True)
        srt_path = out_dir / f"clip_{clip_id}.srt"
        subtitles.write_srt(local_segments, srt_path)

        ass_path = None
        if rs.get("burn_subtitles", True) and local_segments:
            aspect = rs.get("aspect", "9:16")
            res = rendering.ASPECT_RESOLUTIONS.get(aspect, (1080, 1920))
            margin_v = 460 if aspect == "9:16" else 120
            ass_path = str(out_dir / f"clip_{clip_id}.ass")
            subtitles.write_ass(
                local_segments, ass_path, play_res=res,
                style={"margin_v": margin_v, **(rs.get("caption_style") or {})},
            )

        rendering.render_clip(
            source_path=video_path,
            output_path=str(output_path),
            start=start,
            end=end,
            aspect=rs.get("aspect", "9:16"),
            ass_path=ass_path,
            ken_burns=bool(rs.get("ken_burns", True)),
            music_path=rs.get("music_path") or None,
            music_volume=float(rs.get("music_volume", 0.12)),
            overlays=overlays,
            on_progress=prog,
        )

        with SessionLocal() as db:
            c = db.get(Clip, clip_id)
            c.render_status = "rendered"
            c.render_progress = 100.0
            c.output_path = str(output_path)
            c.srt_path = str(srt_path)
            db.commit()

    except Exception as exc:  # noqa: BLE001
        log.exception("clip %s render failed", clip_id)
        with SessionLocal() as db:
            c = db.get(Clip, clip_id)
            if c is not None:
                c.render_status = "failed"
                c.render_error = str(exc)[:2000]
                db.commit()


def merge_clips_task(job_id: str, clip_ids: list[str], new_clip_id: str) -> None:
    """Render any un-rendered members, then concatenate into a new clip."""
    try:
        paths: list[str] = []
        with SessionLocal() as db:
            clips = [db.get(Clip, cid) for cid in clip_ids]
        for c in clips:
            if c is None:
                continue
            if c.render_status != "rendered" or not c.output_path:
                render_clip_task(c.id)
        with SessionLocal() as db:
            for cid in clip_ids:
                c = db.get(Clip, cid)
                if c and c.output_path and Path(c.output_path).exists():
                    paths.append(c.output_path)
        if len(paths) < 2:
            raise media.MediaError("Need at least two rendered clips to merge")

        out_dir = settings.outputs_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"clip_{new_clip_id}.mp4"
        rendering.concat_clips(paths, str(output_path))

        duration, _, _ = media.probe_video(output_path)
        with SessionLocal() as db:
            c = db.get(Clip, new_clip_id)
            if c is not None:
                c.render_status = "rendered"
                c.render_progress = 100.0
                c.end = c.start + duration
                c.output_path = str(output_path)
                db.commit()
    except Exception as exc:  # noqa: BLE001
        log.exception("merge for job %s failed", job_id)
        with SessionLocal() as db:
            c = db.get(Clip, new_clip_id)
            if c is not None:
                c.render_status = "failed"
                c.render_error = str(exc)[:2000]
                db.commit()
