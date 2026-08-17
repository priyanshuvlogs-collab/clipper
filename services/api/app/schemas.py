"""Pydantic schemas for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class JobParams(BaseModel):
    """User-tunable processing parameters submitted with a job."""

    language: str = "auto"                # "auto" | ISO code ("en", "hi", "es", …)
    engine: str = "auto"                  # "auto" | "local" | "groq" | "deepgram" | "assemblyai"
    num_clips: int = Field(default=5, ge=1, le=20)
    min_duration: float = Field(default=15.0, ge=3.0, le=300.0)
    max_duration: float = Field(default=60.0, ge=5.0, le=600.0)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    burn_subtitles: bool = True
    ken_burns: bool = True
    remove_silence: bool = True
    auto_render: bool = True              # render top clips automatically after detection
    music_volume: float = Field(default=0.12, ge=0.0, le=1.0)


class CreateUrlJob(BaseModel):
    url: str
    params: JobParams = JobParams()


class ClipOut(BaseModel):
    id: str
    job_id: str
    order_index: int
    start: float
    end: float
    duration: float
    title: str
    hook_text: str
    transcript: str
    score: float
    score_breakdown: dict[str, Any]
    render_status: str
    render_progress: float
    render_error: str
    render_settings: dict[str, Any]
    overlays: list[dict[str, Any]]
    has_output: bool
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    srt_url: Optional[str] = None

    model_config = {"from_attributes": False}


class JobSummary(BaseModel):
    id: str
    created_at: datetime
    source_type: str
    source: str
    title: str
    status: str
    stage: str
    progress: float
    error: str
    duration: float
    language: str
    transcription_engine: str
    clip_count: int


class JobDetail(JobSummary):
    params: dict[str, Any]
    width: int
    height: int
    language_probability: float
    transcript_text: str
    segments: list[dict[str, Any]]
    clips: list[ClipOut]
    source_video_url: Optional[str] = None
    srt_url: Optional[str] = None
    vtt_url: Optional[str] = None
    txt_url: Optional[str] = None


class ClipUpdate(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title: Optional[str] = None
    order_index: Optional[int] = None
    render_settings: Optional[dict[str, Any]] = None
    overlays: Optional[list[dict[str, Any]]] = None


class ReorderRequest(BaseModel):
    clip_ids: list[str]


class MergeRequest(BaseModel):
    clip_ids: list[str] = Field(min_length=2)
    title: str = "Merged clip"


class RenderRequest(BaseModel):
    aspect: Optional[Literal["9:16", "16:9", "1:1"]] = None
    burn_subtitles: Optional[bool] = None
    ken_burns: Optional[bool] = None
    music_path: Optional[str] = None
    music_volume: Optional[float] = None


class EngineInfo(BaseModel):
    id: str
    name: str
    kind: Literal["local", "remote"]
    available: bool
    detail: str = ""
