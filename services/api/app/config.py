"""Application configuration, loaded from environment variables / .env file."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Storage
    data_dir: Path = Path(os.environ.get("PRO_CLIPPER_DATA", BASE_DIR / "data"))
    database_url: str = ""

    # Server
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_mb: int = 4096

    # Whisper (local, primary)
    whisper_model: str = "small"          # tiny | base | small | medium | large-v3
    whisper_device: str = "auto"          # auto | cpu | cuda
    whisper_compute_type: str = "auto"    # auto | int8 | float16 | float32
    # If local transcription of 1 minute of audio takes longer than this many
    # seconds, remote engines are suggested for the next job.
    whisper_slow_threshold: float = 90.0

    # Remote transcription fallbacks (auto-discovered when keys are present)
    groq_api_key: str = ""
    deepgram_api_key: str = ""
    assemblyai_api_key: str = ""

    # Workers
    worker_count: int = 1

    # --- AI Studio -------------------------------------------------------
    # xAI (Grok): edit plans, image + video generation. Keys can also be
    # saved from the Settings page (stored in <data_dir>/ai_keys.json).
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_text_model: str = "grok-4"
    xai_image_model: str = "grok-imagine-image"
    xai_video_model: str = "grok-imagine-video"
    xai_video_resolution: str = "720p"

    # ElevenLabs: voiceover (TTS), sound effects, music.
    elevenlabs_api_key: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"   # "Rachel" (premade)

    # Spend guard for xAI. Costs are ESTIMATES from the rates below — set
    # them to your account's real prices. 0 budget = no cap.
    ai_budget_usd: float = 0.0
    xai_image_cost_usd: float = 0.07       # per generated image
    xai_video_cost_usd_per_sec: float = 0.05
    xai_text_cost_usd: float = 0.01        # per edit-plan request

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def music_dir(self) -> Path:
        return self.data_dir / "music"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def ai_keys_file(self) -> Path:
        return self.data_dir / "ai_keys.json"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'proclipper.db'}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.sources_dir, self.outputs_dir, self.music_dir, self.assets_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
