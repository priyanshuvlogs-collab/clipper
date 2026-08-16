"""Job endpoints: create (upload / URL), list, inspect, delete, artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Clip, Job
from ..schemas import CreateUrlJob, JobDetail, JobParams, JobSummary
from ..services import ingest
from ..worker import enqueue
from ..services.pipeline import process_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _clip_out(clip: Clip) -> dict:
    has_output = bool(clip.output_path and Path(clip.output_path).exists())
    return {
        "id": clip.id,
        "job_id": clip.job_id,
        "order_index": clip.order_index,
        "start": clip.start,
        "end": clip.end,
        "duration": round(clip.end - clip.start, 3),
        "title": clip.title,
        "hook_text": clip.hook_text,
        "transcript": clip.transcript,
        "score": clip.score,
        "score_breakdown": clip.score_breakdown or {},
        "render_status": clip.render_status,
        "render_progress": clip.render_progress,
        "render_error": clip.render_error,
        "render_settings": clip.render_settings or {},
        "overlays": clip.overlays or [],
        "has_output": has_output,
        "preview_url": f"/api/clips/{clip.id}/video" if has_output else None,
        "download_url": f"/api/clips/{clip.id}/download" if has_output else None,
        "srt_url": f"/api/clips/{clip.id}/srt" if clip.srt_path else None,
    }


def _summary(job: Job) -> dict:
    return {
        "id": job.id,
        "created_at": job.created_at,
        "source_type": job.source_type,
        "source": job.source,
        "title": job.title,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error": job.error,
        "duration": job.duration,
        "language": job.language,
        "transcription_engine": job.transcription_engine,
        "clip_count": len(job.clips),
    }


@router.post("/upload", response_model=JobSummary, status_code=201)
async def create_upload_job(
    file: UploadFile = File(...),
    params: str = Form("{}"),
    db: Session = Depends(get_db),
):
    try:
        parsed = JobParams(**json.loads(params or "{}"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Invalid params: {exc}") from exc

    job = Job(source_type="upload", source=file.filename or "upload.mp4",
              title=Path(file.filename or "upload").stem, params=parsed.model_dump())
    db.add(job)
    db.commit()

    try:
        path = ingest.save_upload(job.id, file.filename or "upload.mp4", file.file)
    except ingest.IngestError as exc:
        db.delete(job)
        db.commit()
        raise HTTPException(415, str(exc)) from exc

    job.video_path = str(path)
    db.commit()
    enqueue(process_job, job.id, name=f"job:{job.id}")
    return _summary(job)


@router.post("/url", response_model=JobSummary, status_code=201)
def create_url_job(body: CreateUrlJob, db: Session = Depends(get_db)):
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "URL must start with http:// or https://")
    source_type = ingest.classify_url(url)
    job = Job(source_type=source_type, source=url, title=url, params=body.params.model_dump())
    db.add(job)
    db.commit()
    enqueue(process_job, job.id, name=f"job:{job.id}")
    return _summary(job)


@router.get("", response_model=list[JobSummary])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    return [_summary(j) for j in jobs]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    detail = _summary(job)
    detail.update(
        {
            "params": job.params or {},
            "width": job.width,
            "height": job.height,
            "language_probability": job.language_probability,
            "transcript_text": job.transcript_text,
            "segments": job.segments or [],
            "clips": [_clip_out(c) for c in sorted(job.clips, key=lambda c: c.order_index)],
            "source_video_url": f"/api/jobs/{job.id}/video" if job.video_path and Path(job.video_path).exists() else None,
            "srt_url": f"/api/jobs/{job.id}/artifacts/srt" if job.srt_path else None,
            "vtt_url": f"/api/jobs/{job.id}/artifacts/vtt" if job.vtt_path else None,
            "txt_url": f"/api/jobs/{job.id}/artifacts/txt" if job.txt_path else None,
        }
    )
    return detail


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    # Best-effort cleanup of media files.
    for p in [job.video_path, job.audio_path, job.srt_path, job.vtt_path, job.txt_path]:
        if p:
            Path(p).unlink(missing_ok=True)
    for clip in job.clips:
        for p in [clip.output_path, clip.srt_path]:
            if p:
                Path(p).unlink(missing_ok=True)
    db.delete(job)
    db.commit()


@router.get("/{job_id}/video")
def stream_source(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or not job.video_path or not Path(job.video_path).exists():
        raise HTTPException(404, "Source video not found")
    return FileResponse(job.video_path, media_type="video/mp4", filename=Path(job.video_path).name)


@router.get("/{job_id}/artifacts/{kind}")
def download_artifact(job_id: str, kind: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    path = {"srt": job.srt_path, "vtt": job.vtt_path, "txt": job.txt_path}.get(kind)
    if not path or not Path(path).exists():
        raise HTTPException(404, f"No {kind} artifact for this job")
    media_types = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}
    return FileResponse(path, media_type=media_types[kind], filename=f"{job_id}_transcript.{kind}")
