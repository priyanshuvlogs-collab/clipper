"""AI Studio endpoints: provider keys / status, generated layers, AI Director."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Asset, Clip
from ..schemas import AiEditRequest, AiKeys, AssetCreate, AssetOut, AssetUpdate
from ..services import ai_keys, ai_studio, elevenlabs
from ..services.ai_keys import AiError

router = APIRouter(prefix="/api", tags=["ai"])


def _asset_out(a: Asset) -> dict:
    ready = a.status == "ready" and bool(a.path) and Path(a.path).exists()
    return {
        "id": a.id, "clip_id": a.clip_id, "kind": a.kind, "provider": a.provider,
        "prompt": a.prompt, "status": a.status, "error": a.error, "duration": a.duration,
        "start": a.start, "end": a.end, "volume": a.volume, "enabled": a.enabled,
        "meta": a.meta or {},
        "file_url": f"/api/assets/{a.id}/file" if ready else None,
    }


def _clip(db: Session, clip_id: str) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


def _asset(db: Session, asset_id: str) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    return asset


def _invalidate_render(clip: Clip) -> None:
    if clip.render_status == "rendered":
        clip.render_status = "detected"


# --- status / keys ------------------------------------------------------------

@router.get("/ai/status")
def ai_status():
    el: dict = {
        "configured": bool(ai_keys.get_key("elevenlabs")),
        "key_hint": ai_keys.hint("elevenlabs"),
        "key_source": ai_keys.source("elevenlabs"),
        "tts_model": settings.elevenlabs_tts_model,
        "credits": None,
        "error": "",
    }
    if el["configured"]:
        try:
            el["credits"] = elevenlabs.credits()
        except AiError as exc:
            el["error"] = str(exc)
    return {
        "xai": {
            "configured": bool(ai_keys.get_key("xai")),
            "key_hint": ai_keys.hint("xai"),
            "key_source": ai_keys.source("xai"),
            "text_model": settings.xai_text_model,
            "image_model": settings.xai_image_model,
            "video_model": settings.xai_video_model,
        },
        "elevenlabs": el,
        "usage": ai_studio.usage_summary(),
        "rates": {
            "image_usd": settings.xai_image_cost_usd,
            "video_usd_per_sec": settings.xai_video_cost_usd_per_sec,
            "plan_usd": settings.xai_text_cost_usd,
        },
    }


@router.put("/ai/keys")
def save_keys(body: AiKeys):
    ai_keys.save_keys({"xai": body.xai_api_key, "elevenlabs": body.elevenlabs_api_key})
    return {"ok": True}


@router.get("/ai/voices")
def voices():
    try:
        return elevenlabs.list_voices()
    except AiError as exc:
        raise HTTPException(400, str(exc)) from exc


# --- assets -------------------------------------------------------------------

@router.get("/clips/{clip_id}/assets", response_model=list[AssetOut])
def list_assets(clip_id: str, db: Session = Depends(get_db)):
    return [_asset_out(a) for a in _clip(db, clip_id).assets]


@router.post("/clips/{clip_id}/assets", response_model=AssetOut, status_code=201)
def create_asset(clip_id: str, body: AssetCreate, db: Session = Depends(get_db)):
    clip = _clip(db, clip_id)
    clip_len = max(0.2, clip.end - clip.start)
    provider = ai_studio.PROVIDER_FOR[body.kind]
    start = min(body.start, max(0.0, clip_len - 0.2))
    if body.end is not None:
        end = min(clip_len, body.end)
        if end <= start:
            raise HTTPException(422, "Layer end must be after its start")
    else:  # per-kind defaults; one-shots (voiceover / sfx) take their real length
        end = {"image": min(clip_len, start + 3.0), "video": min(clip_len, start + 6.0), "music": clip_len}.get(body.kind, 0.0)
    try:
        ai_keys.require_key(provider)
        ai_studio.ensure_budget(body.kind, end - start)
    except AiError as exc:
        raise HTTPException(400, str(exc)) from exc

    asset = Asset(
        clip_id=clip_id, kind=body.kind, provider=provider, prompt=body.prompt.strip(),
        start=round(start, 3), end=round(end, 3),
        volume=body.volume if body.volume is not None else ai_studio.DEFAULT_VOLUME.get(body.kind, 1.0),
        meta={"voice_id": body.voice_id} if body.voice_id else {},
    )
    db.add(asset)
    db.commit()
    ai_studio.start_generation(asset.id)
    return _asset_out(asset)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: str, body: AssetUpdate, db: Session = Depends(get_db)):
    asset = _asset(db, asset_id)
    clip = _clip(db, asset.clip_id)
    clip_len = max(0.2, clip.end - clip.start)
    if body.start is not None:
        asset.start = min(body.start, clip_len)
    if body.end is not None:
        asset.end = min(body.end, clip_len)
    if asset.end < asset.start:
        raise HTTPException(422, "Layer end must be after its start")
    if body.volume is not None:
        asset.volume = body.volume
    if body.enabled is not None:
        asset.enabled = body.enabled
    _invalidate_render(clip)
    db.commit()
    return _asset_out(asset)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset(db, asset_id)
    clip = db.get(Clip, asset.clip_id)
    ai_studio.delete_asset_files(asset)
    db.delete(asset)
    if clip is not None and asset.kind != "plan":
        _invalidate_render(clip)
    db.commit()


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset(db, asset_id)
    if not asset.path or not Path(asset.path).exists():
        raise HTTPException(404, "Asset file is not available")
    media_type = mimetypes.guess_type(asset.path)[0] or "application/octet-stream"
    return FileResponse(asset.path, media_type=media_type)


# --- AI Director --------------------------------------------------------------

@router.post("/clips/{clip_id}/ai-edit", response_model=AssetOut, status_code=202)
def ai_edit(clip_id: str, body: AiEditRequest, db: Session = Depends(get_db)):
    """Let Grok plan the edit, generate the layers and (optionally) render."""
    clip = _clip(db, clip_id)
    if any(a.kind == "plan" and a.status == "pending" for a in clip.assets):
        raise HTTPException(409, "An AI edit is already running for this clip")
    needs_audio = body.voiceover or body.music or body.sfx
    try:
        ai_keys.require_key("xai")
        ai_studio.ensure_budget("plan")
    except AiError as exc:
        raise HTTPException(400, str(exc)) from exc
    opts = body.model_dump()
    if needs_audio and not ai_keys.get_key("elevenlabs"):
        # Degrade gracefully: plan visuals only rather than fail the whole edit.
        opts.update(voiceover=False, music=False, sfx=False)

    plan = Asset(
        clip_id=clip_id, kind="plan", provider="xai",
        prompt=body.instruction.strip() or "Make it as engaging as possible.",
        meta={"stage": "planning"},
    )
    db.add(plan)
    db.commit()
    ai_studio.start_director(plan.id, opts)
    return _asset_out(plan)
