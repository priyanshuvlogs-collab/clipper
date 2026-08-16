# Pro Clipper — AI Video Clipping Studio

Turn long videos into viral **Shorts / Reels / TikToks** in one click.

Pro Clipper ingests a long video (local file, YouTube link, or direct URL), transcribes it
(Hindi, English and 90+ languages), automatically detects the highest-retention moments,
and renders professional vertical clips with burned-in animated captions.

![Stack](https://img.shields.io/badge/Next.js-15-black) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688) ![FFmpeg](https://img.shields.io/badge/FFmpeg-6+-007808) ![Whisper](https://img.shields.io/badge/Faster--Whisper-local-8b5cf6)

---

## Features

| Area | What you get |
| --- | --- |
| **Input** | Drag-and-drop upload (mp4/mov/mkv/webm), YouTube & YouTube Shorts links (yt-dlp), direct video URLs |
| **Transcription** | Faster-Whisper locally (primary) with auto language detection or forced language; full transcript (TXT), timestamped segments, SRT + VTT, word-level timestamps |
| **API auto-discovery** | If local Whisper is unavailable or measured slow, automatically falls back to **Groq Whisper → Deepgram → AssemblyAI** (any engine with an API key set is discovered and usable) |
| **Smart clip detection** | Hook detection (English + Hindi/Hinglish keyword banks), audio energy (RMS), speech rate, keyword salience, silence removal; configurable clip count and min/max duration; every clip is scored and ranked with a full breakdown |
| **Rendering** | 1080p H.264/AAC, 9:16 / 16:9 / 1:1, burned-in short-form captions (styled ASS with pop animation), subtle Ken Burns zoom, background-music bed, text/emoji overlays |
| **Editing** | Timeline view of detected clips, fine start/end trimming (±0.1s nudges), re-ordering, merging multiple clips, per-clip render settings, text overlays with timing/position/size |
| **UI** | Next.js 15 + Tailwind, dark studio theme, live progress bars for every stage, inline preview player per clip, one-click ZIP download of all clips + subtitles |
| **Persistence** | SQLite job history by default (PostgreSQL via `DATABASE_URL`), background worker queue for long videos |

## Project structure

```
pro-clipper/
├── apps/
│   └── web/                     # Next.js 15 (App Router) + TypeScript + Tailwind
│       └── src/
│           ├── app/             # pages: dashboard, /jobs/[id] editor
│           ├── components/      # create-job, clip-card, timeline, ui/* primitives
│           └── lib/             # typed API client
└── services/
    └── api/                     # FastAPI backend
        ├── app/
        │   ├── main.py          # app entrypoint (CORS, routers, worker boot)
        │   ├── config.py        # env-driven settings
        │   ├── database.py      # SQLAlchemy (SQLite / PostgreSQL)
        │   ├── models.py        # Job + Clip tables
        │   ├── schemas.py       # API schemas
        │   ├── worker.py        # background job queue
        │   ├── routers/         # jobs, clips, system endpoints
        │   └── services/
        │       ├── ingest.py          # upload / yt-dlp / direct URL
        │       ├── media.py           # ffprobe, audio extraction, silence detection
        │       ├── transcription.py   # faster-whisper + Groq/Deepgram/AssemblyAI fallbacks
        │       ├── clip_detection.py  # scoring + windowing engine
        │       ├── subtitles.py       # SRT / VTT / TXT / styled ASS
        │       ├── rendering.py       # ffmpeg filter graphs (crop, zoom, captions, music)
        │       └── pipeline.py        # end-to-end job orchestration
        └── requirements.txt
```

## Quick start

### Prerequisites

- **Node.js 20+**, **Python 3.11+**, **FFmpeg** on `PATH` (`ffmpeg -version`)

### 1. Backend

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate   # or: pip install --user
pip install -r requirements.txt
cp .env.example .env                                  # optional: tweak model / API keys
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The first transcription downloads the Whisper model (default `small`). Set
`WHISPER_MODEL=tiny` for fast tests or `large-v3` for maximum accuracy.

### 2. Frontend

```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000  (proxies /api → localhost:8000)
```

Or from the repo root: `npm install && npm run setup:api && npm run dev`.

### 3. Use it

1. Open **http://localhost:3000**
2. Drop a video or paste a YouTube link
3. Pick language (Auto / Hindi / English / …), clip count, durations, format
4. Watch the pipeline: download → transcribe → detect → render
5. Preview, trim, reorder, merge, add overlays — then **Download all**

## Transcription engine fallbacks

Local Faster-Whisper is always tried first. Configure any of these keys and the
engine is auto-discovered and used as a fallback (or on demand via the Engine
selector). If a local run is measured slower than real-time × threshold, remote
engines are preferred automatically for subsequent jobs.

```bash
GROQ_API_KEY=gsk_...        # Groq whisper-large-v3 (generous free tier)
DEEPGRAM_API_KEY=...        # Deepgram Nova-2 (free credits)
ASSEMBLYAI_API_KEY=...      # AssemblyAI (free tier)
```

Check availability anytime: `GET /api/engines`.

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/jobs/upload` | Create job from an uploaded file (multipart + `params` JSON) |
| `POST` | `/api/jobs/url` | Create job from a YouTube / direct URL |
| `GET` | `/api/jobs` · `/api/jobs/{id}` | Job history / detail (progress, transcript, clips) |
| `GET` | `/api/jobs/{id}/artifacts/{srt\|vtt\|txt}` | Download transcript artifacts |
| `GET` | `/api/jobs/{id}/download-all` | ZIP of all rendered clips + subtitles |
| `PATCH` | `/api/clips/{id}` | Edit trim, title, order, render settings, overlays |
| `POST` | `/api/clips/{id}/render` | Render / re-render a clip |
| `POST` | `/api/jobs/{id}/clips/reorder` | Reorder clips |
| `POST` | `/api/jobs/{id}/clips/merge` | Merge clips into a new one |
| `GET` | `/api/clips/{id}/video` · `/download` · `/srt` | Stream / download clip assets |
| `GET` | `/api/engines` · `/api/health` | Engine discovery / health |

Interactive docs: **http://localhost:8000/docs**

## Configuration reference

All settings via environment variables (see `services/api/.env.example`):

| Variable | Default | Description |
| --- | --- | --- |
| `WHISPER_MODEL` | `small` | tiny / base / small / medium / large-v3 |
| `WHISPER_DEVICE` | `auto` | cpu / cuda |
| `DATABASE_URL` | SQLite | e.g. `postgresql+psycopg://…` |
| `PRO_CLIPPER_DATA` | `services/api/data` | media + database storage root |
| `WORKER_COUNT` | `1` | parallel background workers |
| `CORS_ORIGINS` | localhost:3000 | comma-separated origins |

Background music: drop `.mp3`/`.wav` files into `services/api/data/music/` and set a
clip's `render_settings.music_path` (via `PATCH /api/clips/{id}`).
