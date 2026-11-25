/** Typed client for the Pro Clipper API (proxied through /api rewrites). */

export interface JobParams {
  language: string;
  engine: string;
  num_clips: number;
  min_duration: number;
  max_duration: number;
  aspect: "9:16" | "16:9" | "1:1";
  burn_subtitles: boolean;
  ken_burns: boolean;
  remove_silence: boolean;
  auto_render: boolean;
  music_volume: number;
}

export const DEFAULT_PARAMS: JobParams = {
  language: "auto",
  engine: "auto",
  num_clips: 5,
  min_duration: 15,
  max_duration: 60,
  aspect: "9:16",
  burn_subtitles: true,
  ken_burns: true,
  remove_silence: true,
  auto_render: true,
  music_volume: 0.12,
};

export interface Overlay {
  text: string;
  start: number;
  end: number;
  x: number; // 0-100 (% of width)
  y: number; // 0-100 (% of height)
  size: number;
  color: string;
}

export interface ClipData {
  id: string;
  job_id: string;
  order_index: number;
  start: number;
  end: number;
  duration: number;
  title: string;
  hook_text: string;
  transcript: string;
  score: number;
  score_breakdown: Record<string, number>;
  render_status: "detected" | "rendering" | "rendered" | "failed";
  render_progress: number;
  render_error: string;
  render_settings: Record<string, unknown>;
  overlays: Overlay[];
  has_output: boolean;
  preview_url: string | null;
  download_url: string | null;
  srt_url: string | null;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  words: { start: number; end: number; word: string }[];
}

export interface JobSummary {
  id: string;
  created_at: string;
  source_type: string;
  source: string;
  title: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  error: string;
  duration: number;
  language: string;
  transcription_engine: string;
  clip_count: number;
}

export interface JobDetail extends JobSummary {
  params: Partial<JobParams>;
  width: number;
  height: number;
  language_probability: number;
  transcript_text: string;
  segments: Segment[];
  clips: ClipData[];
  source_video_url: string | null;
  srt_url: string | null;
  vtt_url: string | null;
  txt_url: string | null;
}

export interface EngineInfo {
  id: string;
  name: string;
  kind: "local" | "remote";
  available: boolean;
  detail: string;
}

export type AssetKind = "image" | "video" | "voiceover" | "sfx" | "music";

export interface PlanData {
  title?: string;
  notes?: string;
  overlays?: { text: string; start: number; end: number }[];
  broll?: { type: string; start: number; end: number; prompt: string }[];
  sfx?: { at: number; prompt: string }[];
  music_prompt?: string | null;
  voiceover_script?: string | null;
}

export interface AssetData {
  id: string;
  clip_id: string;
  kind: AssetKind | "plan";
  provider: "xai" | "elevenlabs";
  prompt: string;
  status: "pending" | "ready" | "failed";
  error: string;
  duration: number;
  start: number;
  end: number;
  volume: number;
  enabled: boolean;
  meta: { stage?: string; generated?: number; failed?: number; plan?: PlanData; voice_id?: string };
  file_url: string | null;
}

export interface AiEditOptions {
  instruction: string;
  broll_images: boolean;
  broll_video: boolean;
  voiceover: boolean;
  music: boolean;
  sfx: boolean;
  auto_render: boolean;
  voice_id?: string;
}

export interface Voice {
  voice_id: string;
  name: string;
  description: string;
  preview_url: string;
}

export interface AiStatus {
  xai: {
    configured: boolean;
    key_hint: string;
    key_source: "" | "saved" | "env";
    text_model: string;
    image_model: string;
    video_model: string;
  };
  elevenlabs: {
    configured: boolean;
    key_hint: string;
    key_source: "" | "saved" | "env";
    tts_model: string;
    credits: { used: number; limit: number; remaining: number; tier: string } | null;
    error: string;
  };
  anthropic: { configured: boolean; key_hint: string; key_source: "" | "saved" | "env"; model: string };
  planner: "" | "anthropic" | "xai";
  usage: {
    anthropic_est_usd: number;
    items: { provider: string; kind: string; count: number; units: number; est_cost_usd: number }[];
    xai_est_usd: number;
    budget_usd: number;
  };
  rates: { image_usd: number; video_usd_per_sec: number; plan_usd: number };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** Stream a help-assistant reply; `onText` receives each new piece of text. */
export async function streamHelpChat(
  body: { messages: ChatMessage[]; page: string; job_id?: string },
  onText: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText || "The help assistant is unavailable";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as { text?: string; error?: string; done?: boolean };
      if (event.error) throw new Error(event.error);
      if (event.text) onText(event.text);
    }
    if (done) break;
  }
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listJobs: () => fetch("/api/jobs").then((r) => handle<JobSummary[]>(r)),
  getJob: (id: string) => fetch(`/api/jobs/${id}`).then((r) => handle<JobDetail>(r)),
  deleteJob: (id: string) => fetch(`/api/jobs/${id}`, { method: "DELETE" }).then((r) => handle<void>(r)),

  createUrlJob: (url: string, params: JobParams) =>
    fetch("/api/jobs/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, params }),
    }).then((r) => handle<JobSummary>(r)),

  uploadJob: (file: File, params: JobParams) => {
    const form = new FormData();
    form.append("file", file);
    form.append("params", JSON.stringify(params));
    return fetch("/api/jobs/upload", { method: "POST", body: form }).then((r) => handle<JobSummary>(r));
  },

  updateClip: (id: string, body: Partial<Pick<ClipData, "start" | "end" | "title" | "order_index" | "render_settings" | "overlays">>) =>
    fetch(`/api/clips/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => handle<ClipData>(r)),

  renderClip: (id: string, settings?: Record<string, unknown>) =>
    fetch(`/api/clips/${id}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings ?? {}),
    }).then((r) => handle<ClipData>(r)),

  deleteClip: (id: string) => fetch(`/api/clips/${id}`, { method: "DELETE" }).then((r) => handle<void>(r)),

  reorderClips: (jobId: string, clipIds: string[]) =>
    fetch(`/api/jobs/${jobId}/clips/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_ids: clipIds }),
    }).then((r) => handle<{ ok: boolean }>(r)),

  mergeClips: (jobId: string, clipIds: string[], title: string) =>
    fetch(`/api/jobs/${jobId}/clips/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_ids: clipIds, title }),
    }).then((r) => handle<ClipData>(r)),

  aiStatus: () => fetch("/api/ai/status").then((r) => handle<AiStatus>(r)),
  saveAiKeys: (keys: { xai_api_key?: string; elevenlabs_api_key?: string; anthropic_api_key?: string }) =>
    fetch("/api/ai/keys", json("PUT", keys)).then((r) => handle<{ ok: boolean }>(r)),
  voices: () => fetch("/api/ai/voices").then((r) => handle<Voice[]>(r)),

  listAssets: (clipId: string) => fetch(`/api/clips/${clipId}/assets`).then((r) => handle<AssetData[]>(r)),
  createAsset: (
    clipId: string,
    body: { kind: AssetKind; prompt: string; start: number; end?: number; voice_id?: string },
  ) => fetch(`/api/clips/${clipId}/assets`, json("POST", body)).then((r) => handle<AssetData>(r)),
  updateAsset: (id: string, body: Partial<Pick<AssetData, "start" | "end" | "volume" | "enabled">>) =>
    fetch(`/api/assets/${id}`, json("PATCH", body)).then((r) => handle<AssetData>(r)),
  deleteAsset: (id: string) => fetch(`/api/assets/${id}`, { method: "DELETE" }).then((r) => handle<void>(r)),
  aiEdit: (clipId: string, opts: AiEditOptions) =>
    fetch(`/api/clips/${clipId}/ai-edit`, json("POST", opts)).then((r) => handle<AssetData>(r)),

  engines: () => fetch("/api/engines").then((r) => handle<EngineInfo[]>(r)),
};
