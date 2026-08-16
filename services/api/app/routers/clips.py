"""Clip endpoints: edit (trim / reorder / overlays), render, merge, download."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Clip, Job
from ..schemas import ClipOut, ClipUpdate, MergeRequest, RenderRequest, ReorderRequest
from ..services.pipeline import merge_clips_task, render_clip_task
from ..worker import enqueue
from .jobs import _clip_out

router = APIRouter(prefix="/api", tags=["clips"])


def _get_clip(db: Session, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


@router.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: str, body: ClipUpdate, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    job = db.get(Job, clip.job_id)

    if body.start is not None:
        clip.start = max(0.0, float(body.start))
    if body.end is not None:
        upper = job.duration if job and job.duration else float(body.end)
        clip.end = min(float(body.end), upper) if upper else float(body.end)
    if clip.end <= clip.start:
        raise HTTPException(422, "Clip end must be after start")
    if body.title is not None:
        clip.title = body.title
    if body.order_index is not None:
        clip.order_index = int(body.order_index)
    if body.render_settings is not None:
        clip.render_settings = {**(clip.render_settings or {}), **body.render_settings}
    if body.overlays is not None:
        clip.overlays = body.overlays

    # Timing / style edits invalidate any previous render.
    if any(v is not None for v in (body.start, body.end, body.render_settings, body.overlays)):
        if clip.render_status == "rendered":
            clip.render_status = "detected"
            clip.render_progress = 0.0
    db.commit()
    return _clip_out(clip)


@router.post("/jobs/{job_id}/clips/reorder")
def reorder_clips(job_id: str, body: ReorderRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    position = {cid: i for i, cid in enumerate(body.clip_ids)}
    for clip in job.clips:
        if clip.id in position:
            clip.order_index = position[clip.id]
    db.commit()
    return {"ok": True}


@router.post("/clips/{clip_id}/render", response_model=ClipOut)
def render_clip(clip_id: str, body: RenderRequest | None = None, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    if clip.render_status == "rendering":
        raise HTTPException(409, "Clip is already rendering")
    if body:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            clip.render_settings = {**(clip.render_settings or {}), **updates}
    clip.render_status = "rendering"
    clip.render_progress = 0.0
    clip.render_error = ""
    db.commit()
    enqueue(render_clip_task, clip.id, name=f"render:{clip.id}")
    return _clip_out(clip)


@router.post("/jobs/{job_id}/clips/merge", response_model=ClipOut, status_code=201)
def merge_clips(job_id: str, body: MergeRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    members = [c for c in job.clips if c.id in set(body.clip_ids)]
    if len(members) < 2:
        raise HTTPException(422, "Select at least two clips belonging to this job")
    members.sort(key=lambda c: body.clip_ids.index(c.id))

    merged = Clip(
        job_id=job_id,
        order_index=max((c.order_index for c in job.clips), default=0) + 1,
        start=members[0].start,
        end=members[0].end,  # corrected after concat with the real duration
        title=body.title,
        transcript=" ".join(c.transcript for c in members),
        score=max(c.score for c in members),
        score_breakdown={"merged_from": len(members)},
        render_status="rendering",
        render_settings=dict(members[0].render_settings or {}),
    )
    db.add(merged)
    db.commit()
    enqueue(merge_clips_task, job_id, [c.id for c in members], merged.id, name=f"merge:{merged.id}")
    return _clip_out(merged)


@router.delete("/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    for p in [clip.output_path, clip.srt_path]:
        if p:
            Path(p).unlink(missing_ok=True)
    db.delete(clip)
    db.commit()


@router.get("/clips/{clip_id}/video")
def stream_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    if not clip.output_path or not Path(clip.output_path).exists():
        raise HTTPException(404, "Clip has not been rendered yet")
    return FileResponse(clip.output_path, media_type="video/mp4")


@router.get("/clips/{clip_id}/download")
def download_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    if not clip.output_path or not Path(clip.output_path).exists():
        raise HTTPException(404, "Clip has not been rendered yet")
    safe_title = "".join(ch for ch in clip.title if ch.isalnum() or ch in " -_")[:50].strip() or clip.id
    return FileResponse(clip.output_path, media_type="video/mp4", filename=f"{safe_title}.mp4")


@router.get("/clips/{clip_id}/srt")
def download_clip_srt(clip_id: str, db: Session = Depends(get_db)):
    clip = _get_clip(db, clip_id)
    if not clip.srt_path or not Path(clip.srt_path).exists():
        raise HTTPException(404, "No subtitles for this clip yet")
    return FileResponse(clip.srt_path, media_type="application/x-subrip", filename=f"clip_{clip_id}.srt")


@router.get("/jobs/{job_id}/download-all")
def download_all(job_id: str, db: Session = Depends(get_db)):
    """One-click ZIP of every rendered clip + subtitles + full transcript."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    buf = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, clip in enumerate(sorted(job.clips, key=lambda c: c.order_index), start=1):
            base = f"clip_{i:02d}"
            if clip.output_path and Path(clip.output_path).exists():
                zf.write(clip.output_path, f"{base}.mp4")
                added += 1
            if clip.srt_path and Path(clip.srt_path).exists():
                zf.write(clip.srt_path, f"{base}.srt")
        for path, name in [
            (job.srt_path, "transcript.srt"),
            (job.vtt_path, "transcript.vtt"),
            (job.txt_path, "transcript.txt"),
        ]:
            if path and Path(path).exists():
                zf.write(path, name)
    if added == 0 and not job.txt_path:
        raise HTTPException(404, "Nothing to download yet")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="proclipper_{job_id}.zip"'},
    )
