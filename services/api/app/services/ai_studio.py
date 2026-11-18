"""AI Studio: generate media layers for a clip and run the "AI Director".

- B-roll images / video  -> xAI (Grok Imagine)
- Voiceover / SFX / music -> ElevenLabs
- AI Director             -> Grok reads the clip transcript, returns an edit
                             plan (title, text overlays, B-roll, SFX, music,
                             optional voiceover) which is applied and rendered.

Generation runs on its own daemon threads so slow provider calls (video can
take minutes) never block the render queue.
"""

from __future__ import annotations

import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from ..config import settings
from ..database import SessionLocal
from ..models import AiUsage, Asset, Clip, Job
from . import elevenlabs, media, xai
from .ai_keys import AiError

log = logging.getLogger("proclipper.ai")

PROVIDER_FOR = {"image": "xai", "video": "xai", "plan": "xai", "voiceover": "elevenlabs", "sfx": "elevenlabs", "music": "elevenlabs"}
DEFAULT_VOLUME = {"voiceover": 1.0, "sfx": 0.8, "music": 0.15}
STYLE_SUFFIX = "Cinematic, high detail, no text, no watermark, no logos."


# --- usage / budget -----------------------------------------------------------

def xai_spend() -> float:
    with SessionLocal() as db:
        total = db.scalar(select(func.sum(AiUsage.est_cost_usd)).where(AiUsage.provider == "xai"))
    return float(total or 0.0)


def estimate_cost(kind: str, seconds: float = 0.0) -> float:
    if kind == "image":
        return settings.xai_image_cost_usd
    if kind == "video":
        return settings.xai_video_cost_usd_per_sec * max(1.0, min(15.0, round(seconds)))
    if kind == "plan":
        return settings.xai_text_cost_usd
    return 0.0


def ensure_budget(kind: str, seconds: float = 0.0) -> None:
    budget = settings.ai_budget_usd
    if budget <= 0 or PROVIDER_FOR.get(kind) != "xai":
        return
    cost = estimate_cost(kind, seconds)
    spent = xai_spend()
    if spent + cost > budget + 1e-9:
        raise AiError(
            f"AI budget reached: ~${spent:.2f} of ${budget:.2f} spent and this would add ~${cost:.2f}. "
            "Raise AI_BUDGET_USD to continue."
        )


def _record(provider: str, kind: str, units: float, cost: float = 0.0) -> None:
    with SessionLocal() as db:
        db.add(AiUsage(provider=provider, kind=kind, units=units, est_cost_usd=cost))
        db.commit()


def usage_summary() -> dict[str, Any]:
    with SessionLocal() as db:
        rows = db.execute(
            select(AiUsage.provider, AiUsage.kind, func.count(), func.sum(AiUsage.units), func.sum(AiUsage.est_cost_usd))
            .group_by(AiUsage.provider, AiUsage.kind)
        ).all()
    items = [
        {"provider": p, "kind": k, "count": int(n), "units": round(float(u or 0), 1), "est_cost_usd": round(float(c or 0), 4)}
        for p, k, n, u, c in rows
    ]
    return {
        "items": items,
        "xai_est_usd": round(sum(i["est_cost_usd"] for i in items if i["provider"] == "xai"), 4),
        "budget_usd": settings.ai_budget_usd,
    }


# --- asset generation ---------------------------------------------------------

def asset_dir(clip_id: str) -> Path:
    d = settings.assets_dir / clip_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _image_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _set(asset_id: str, **fields) -> None:
    with SessionLocal() as db:
        a = db.get(Asset, asset_id)
        if a is None:
            return
        for k, v in fields.items():
            setattr(a, k, v)
        db.commit()


def generate_asset(asset_id: str) -> None:
    """Call the provider for one pending asset and store the result."""
    with SessionLocal() as db:
        a = db.get(Asset, asset_id)
        if a is None:
            return
        clip = db.get(Clip, a.clip_id)
        if clip is None:
            return
        kind, prompt, clip_id = a.kind, a.prompt, a.clip_id
        start, end = a.start, a.end
        meta = dict(a.meta or {})
        aspect = (clip.render_settings or {}).get("aspect", "9:16")
        clip_len = max(0.2, clip.end - clip.start)

    slot = max(0.0, end - start)
    try:
        ensure_budget(kind, slot)
        if kind == "image":
            data = xai.generate_image(f"{prompt}. {STYLE_SUFFIX}", aspect)
            ext, units, cost = _image_ext(data), 1.0, estimate_cost("image")
        elif kind == "video":
            data = xai.generate_video(f"{prompt}. {STYLE_SUFFIX}", slot or 6.0, aspect)
            ext, units, cost = "mp4", max(1.0, round(slot or 6.0)), estimate_cost("video", slot or 6.0)
        elif kind == "voiceover":
            data = elevenlabs.text_to_speech(prompt, meta.get("voice_id") or None)
            ext, units, cost = "mp3", float(len(prompt)), 0.0
        elif kind == "sfx":
            data = elevenlabs.sound_effect(prompt, slot or None)
            ext, units, cost = "mp3", 1.0, 0.0
        elif kind == "music":
            data = elevenlabs.music(prompt, slot or clip_len)
            ext, units, cost = "mp3", max(10.0, slot or clip_len), 0.0
        else:
            raise AiError(f"Unknown asset kind: {kind}")
        if not data:
            raise AiError("The provider returned an empty file")

        path = asset_dir(clip_id) / f"{asset_id}.{ext}"
        path.write_bytes(data)
        _record(PROVIDER_FOR[kind], kind, units, cost)

        duration = 0.0
        if kind != "image":
            try:
                duration, _, _ = media.probe_video(path)
            except media.MediaError as exc:
                path.unlink(missing_ok=True)
                raise AiError("The generated file is not valid media") from exc
        # Audio one-shots and video run for their real length unless a slot was given.
        if kind in ("voiceover", "sfx", "video") and duration > 0:
            end = min(clip_len, start + (min(slot, duration) if slot > 0 else duration))
        elif end <= start:
            end = min(clip_len, start + (3.0 if kind == "image" else clip_len))
        _set(asset_id, status="ready", path=str(path), duration=round(duration, 3), end=round(end, 3), error="")
        _mark_stale(clip_id)
    except Exception as exc:  # noqa: BLE001 — persisted for the UI
        if not isinstance(exc, AiError):
            log.exception("asset %s generation crashed", asset_id)
        _set(asset_id, status="failed", error=str(exc)[:1000])


def _mark_stale(clip_id: str) -> None:
    """A finished layer means the last render no longer matches the clip."""
    with SessionLocal() as db:
        c = db.get(Clip, clip_id)
        if c is not None and c.render_status == "rendered":
            c.render_status = "detected"
            db.commit()


def start_generation(asset_id: str) -> None:
    threading.Thread(target=generate_asset, args=(asset_id,), daemon=True, name=f"ai-asset-{asset_id[:8]}").start()


def delete_asset_files(asset: Asset) -> None:
    if asset.path:
        Path(asset.path).unlink(missing_ok=True)


def delete_clip_assets(clip_id: str) -> None:
    shutil.rmtree(settings.assets_dir / clip_id, ignore_errors=True)


# --- AI Director --------------------------------------------------------------

DIRECTOR_SYSTEM = """You are a senior short-form video editor (Shorts / Reels / TikTok).
You receive one clip: its length, aspect ratio and transcript with timestamps in
seconds relative to the clip start. Design edits that raise retention.
Reply with ONE JSON object and nothing else:
{
  "title": "catchy title, max 60 chars, same language as the transcript",
  "overlays": [{"text": "max 5 words or one emoji", "start": 0.0, "end": 2.5, "y": 15}],
  "broll": [{"type": "image" | "video", "start": 4.0, "end": 7.0, "prompt": "vivid visual description in English"}],
  "sfx": [{"at": 0.0, "prompt": "short sound description in English"}],
  "music_prompt": "instrumental style description in English, or null",
  "voiceover_script": "narration text, or null",
  "notes": "one sentence explaining the edit"
}
Rules: all times must lie inside the clip. First overlay is a hook in the first
3 seconds. B-roll illustrates what is being said at that moment, each 2-5 s,
never covering the first 1.5 s, never overlapping. Use only the feature lists
you are told are enabled and leave the others empty / null. Keep it tasteful:
fewer, well-placed edits beat many."""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_plan(raw: dict[str, Any], clip_len: float, opts: dict[str, Any]) -> dict[str, Any]:
    """Clamp an LLM plan to the clip and to the features the user enabled."""
    plan: dict[str, Any] = {
        "title": str(raw.get("title") or "").strip()[:80],
        "notes": str(raw.get("notes") or "").strip()[:400],
        "overlays": [], "broll": [], "sfx": [], "music_prompt": None, "voiceover_script": None,
    }
    for ov in (raw.get("overlays") or [])[:4]:
        if not isinstance(ov, dict):
            continue
        text = str(ov.get("text") or "").strip()[:60]
        s = max(0.0, min(_f(ov.get("start")), clip_len - 0.5))
        e = max(s + 0.5, min(_f(ov.get("end"), s + 2.5), clip_len))
        if text:
            plan["overlays"].append({"text": text, "start": round(s, 2), "end": round(e, 2), "y": max(5.0, min(_f(ov.get("y"), 15), 90.0))})

    cursor = 0.0
    for br in sorted((b for b in (raw.get("broll") or []) if isinstance(b, dict)), key=lambda b: _f(b.get("start")))[:5]:
        kind = "video" if str(br.get("type")) == "video" else "image"
        if kind == "video" and not opts.get("broll_video"):
            kind = "image"
        if kind == "image" and not opts.get("broll_images"):
            if not opts.get("broll_video"):
                continue
            kind = "video"
        prompt = str(br.get("prompt") or "").strip()[:600]
        s = max(cursor, min(_f(br.get("start")), clip_len))
        e = min(clip_len, max(s + 1.5, min(_f(br.get("end"), s + 3), s + 8.0)))
        if not prompt or e - s < 1.0:
            continue
        plan["broll"].append({"type": kind, "start": round(s, 2), "end": round(e, 2), "prompt": prompt})
        cursor = e
        if len(plan["broll"]) >= 4:
            break

    if opts.get("sfx"):
        for fx in (raw.get("sfx") or [])[:3]:
            if isinstance(fx, dict) and str(fx.get("prompt") or "").strip():
                at = max(0.0, min(_f(fx.get("at")), clip_len - 0.3))
                plan["sfx"].append({"at": round(at, 2), "prompt": str(fx["prompt"]).strip()[:300]})
    if opts.get("music") and raw.get("music_prompt"):
        plan["music_prompt"] = str(raw["music_prompt"]).strip()[:500]
    if opts.get("voiceover") and raw.get("voiceover_script"):
        plan["voiceover_script"] = str(raw["voiceover_script"]).strip()[:2500]
    return plan


def _clip_context(clip: Clip, job: Job | None) -> str:
    lines: list[str] = []
    for seg in (job.segments if job else None) or []:
        s, e = _f(seg.get("start")), _f(seg.get("end"))
        if e <= clip.start or s >= clip.end:
            continue
        lines.append(f"[{max(0.0, s - clip.start):.1f}-{min(clip.end, e) - clip.start:.1f}] {str(seg.get('text', '')).strip()}")
    return "\n".join(lines) or clip.transcript or "(no speech detected)"


def run_director(plan_id: str, opts: dict[str, Any]) -> None:
    """Plan -> apply -> generate layers -> (optionally) render. Thread target."""
    from .pipeline import render_clip_task  # local import: pipeline imports models only

    try:
        with SessionLocal() as db:
            plan_asset = db.get(Asset, plan_id)
            clip = db.get(Clip, plan_asset.clip_id) if plan_asset else None
            if clip is None:
                return
            clip_id = clip.id
            clip_len = max(0.2, clip.end - clip.start)
            job = db.get(Job, clip.job_id)
            enabled = [k for k in ("broll_images", "broll_video", "voiceover", "music", "sfx") if opts.get(k)]
            user_msg = (
                f"Clip length: {clip_len:.1f}s. Aspect: {(clip.render_settings or {}).get('aspect', '9:16')}. "
                f"Language: {(job.language if job else '') or 'unknown'}.\n"
                f"Enabled features: text overlays, {', '.join(enabled) or 'none'}.\n"
                f"Editor's instruction: {opts.get('instruction') or 'Make it as engaging as possible.'}\n\n"
                f"Transcript:\n{_clip_context(clip, job)[:6000]}"
            )

        ensure_budget("plan")
        raw = xai.chat_json(DIRECTOR_SYSTEM, user_msg)
        _record("xai", "plan", 1.0, estimate_cost("plan"))
        plan = sanitize_plan(raw, clip_len, opts)

        # Apply the plan: replace whatever a previous Director run produced.
        new_ids: list[str] = []
        with SessionLocal() as db:
            clip = db.get(Clip, clip_id)
            if clip is None:
                return
            for old in db.query(Asset).filter(Asset.clip_id == clip_id, Asset.id != plan_id).all():
                if (old.meta or {}).get("plan_id") or old.kind == "plan":
                    delete_asset_files(old)
                    db.delete(old)
            if plan["title"]:
                clip.title = plan["title"]
            kept = [o for o in (clip.overlays or []) if not o.get("ai")]
            clip.overlays = kept + [
                {"text": o["text"], "start": o["start"], "end": o["end"], "x": 50, "y": o["y"],
                 "size": 96 if len(o["text"]) <= 2 else 64, "color": "white", "ai": True}
                for o in plan["overlays"]
            ]
            if plan["voiceover_script"]:
                clip.render_settings = {**(clip.render_settings or {}), "original_volume": 0.15}

            def add(kind: str, prompt: str, start: float, end: float, **meta: Any) -> None:
                a = Asset(
                    clip_id=clip_id, kind=kind, provider=PROVIDER_FOR[kind], prompt=prompt,
                    start=start, end=end, volume=DEFAULT_VOLUME.get(kind, 1.0),
                    meta={"plan_id": plan_id, **meta},
                )
                db.add(a)
                db.flush()
                new_ids.append(a.id)

            for br in plan["broll"]:
                add(br["type"], br["prompt"], br["start"], br["end"])
            for fx in plan["sfx"]:
                add("sfx", fx["prompt"], fx["at"], 0.0)
            if plan["music_prompt"]:
                add("music", plan["music_prompt"], 0.0, round(clip_len, 3))
            if plan["voiceover_script"]:
                add("voiceover", plan["voiceover_script"], 0.0, 0.0, voice_id=opts.get("voice_id") or "")
            db.commit()

        _set(plan_id, meta={"plan": plan, "stage": "generating"})
        if new_ids:
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(generate_asset, new_ids))

        with SessionLocal() as db:
            failed = db.query(Asset).filter(Asset.id.in_(new_ids), Asset.status == "failed").count() if new_ids else 0
        _set(
            plan_id, status="ready",
            meta={"plan": plan, "stage": "done", "generated": len(new_ids) - failed, "failed": failed},
        )
        if opts.get("auto_render", True):
            render_clip_task(clip_id)
    except Exception as exc:  # noqa: BLE001
        if not isinstance(exc, AiError):
            log.exception("AI director run %s crashed", plan_id)
        _set(plan_id, status="failed", error=str(exc)[:1000])


def start_director(plan_id: str, opts: dict[str, Any]) -> None:
    threading.Thread(target=run_director, args=(plan_id, opts), daemon=True, name=f"ai-director-{plan_id[:8]}").start()

