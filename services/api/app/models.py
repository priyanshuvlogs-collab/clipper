"""Database models: jobs (one per source video) and clips (detected moments)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """A processing job for one source video (upload / YouTube / direct URL)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    # Input
    source_type: Mapped[str] = mapped_column(String(16))  # upload | youtube | url
    source: Mapped[str] = mapped_column(Text)             # original filename or URL
    title: Mapped[str] = mapped_column(Text, default="")

    # Lifecycle
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed|cancelled
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    # queued | downloading | probing | extracting_audio | transcribing | detecting | rendering | completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    error: Mapped[str] = mapped_column(Text, default="")

    # User-tunable parameters (language, clip count, durations, render options…)
    params: Mapped[dict] = mapped_column(JSON, default=dict)

    # Media facts
    video_path: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)

    # Transcription results
    language: Mapped[str] = mapped_column(String(8), default="")
    language_probability: Mapped[float] = mapped_column(Float, default=0.0)
    transcription_engine: Mapped[str] = mapped_column(String(32), default="")
    transcript_text: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[list] = mapped_column(JSON, default=list)  # [{start,end,text,words:[{start,end,word}]}]
    srt_path: Mapped[str] = mapped_column(Text, default="")
    vtt_path: Mapped[str] = mapped_column(Text, default="")
    txt_path: Mapped[str] = mapped_column(Text, default="")

    clips: Mapped[list["Clip"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Clip.order_index"
    )


class Clip(Base):
    """A detected (and possibly user-edited) highlight inside a job's video."""

    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    order_index: Mapped[int] = mapped_column(Integer, default=0)
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)

    title: Mapped[str] = mapped_column(Text, default="")
    hook_text: Mapped[str] = mapped_column(Text, default="")   # first sentence / opening hook
    transcript: Mapped[str] = mapped_column(Text, default="")  # text within [start, end]

    # Ranking
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

    # Render state
    render_status: Mapped[str] = mapped_column(String(16), default="detected")
    # detected | rendering | rendered | failed
    render_progress: Mapped[float] = mapped_column(Float, default=0.0)
    render_error: Mapped[str] = mapped_column(Text, default="")
    render_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    # {aspect: "9:16"|"16:9", burn_subtitles: bool, ken_burns: bool,
    #  music_path: str, music_volume: float, caption_style: {...}}
    overlays: Mapped[list] = mapped_column(JSON, default=list)
    # [{text, start, end, x, y, size, color, emoji?}] — drawtext overlays

    output_path: Mapped[str] = mapped_column(Text, default="")
    srt_path: Mapped[str] = mapped_column(Text, default="")

    job: Mapped[Job] = relationship(back_populates="clips")
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="clip", cascade="all, delete-orphan", order_by="Asset.created_at"
    )


class Asset(Base):
    """An AI-generated media layer attached to a clip.

    kind: image | video (B-roll, xAI) · voiceover | sfx | music (ElevenLabs)
          · plan (an AI Director run; never rendered, `meta` holds the plan)
    `start` / `end` are seconds relative to the clip's own start.
    """

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(16))          # xai | elevenlabs
    prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | ready | failed
    error: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[float] = mapped_column(Float, default=0.0)

    start: Mapped[float] = mapped_column(Float, default=0.0)
    end: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(default=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    clip: Mapped[Clip] = relationship(back_populates="assets")


class AiUsage(Base):
    """One billable AI call, for the spend / credits meter."""

    __tablename__ = "ai_usage"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    provider: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    units: Mapped[float] = mapped_column(Float, default=0.0)   # images, seconds, characters…
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
