"""System endpoints: health check and transcription-engine discovery."""

from __future__ import annotations

import shutil

from fastapi import APIRouter

from ..schemas import EngineInfo
from ..services.transcription import discover_engines
from ..worker import pending_count

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "queued_tasks": pending_count(),
    }


@router.get("/engines", response_model=list[EngineInfo])
def engines():
    return discover_engines()
