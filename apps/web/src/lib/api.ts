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

  engines: () => fetch("/api/engines").then((r) => handle<EngineInfo[]>(r)),
};
