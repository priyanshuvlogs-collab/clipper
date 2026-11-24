"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AudioLines,
  Clapperboard,
  Image as ImageIcon,
  Loader2,
  Mic,
  Music,
  RefreshCw,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import {
  api,
  type AiEditOptions,
  type AiStatus,
  type AssetData,
  type AssetKind,
  type ClipData,
  type Voice,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const KINDS: Record<AssetKind, { label: string; icon: typeof Mic; placeholder: string; provider: "xai" | "elevenlabs" }> = {
  image: { label: "B-roll image", icon: ImageIcon, placeholder: "A neon city skyline at night, drone shot", provider: "xai" },
  video: { label: "B-roll video", icon: Clapperboard, placeholder: "Slow-motion coins falling onto a glass table", provider: "xai" },
  voiceover: { label: "Voiceover", icon: Mic, placeholder: "The script to speak (any language)…", provider: "elevenlabs" },
  music: { label: "Music", icon: Music, placeholder: "Upbeat lo-fi hip hop, no vocals", provider: "elevenlabs" },
  sfx: { label: "Sound effect", icon: AudioLines, placeholder: "Deep cinematic whoosh", provider: "elevenlabs" },
};

const isAudio = (k: string) => k === "voiceover" || k === "music" || k === "sfx";

const textareaClass =
  "w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground placeholder:text-muted/70 focus:border-primary/60 focus:outline-none focus:ring-2 focus:ring-primary/20";

export function AiStudio({ clip, onChanged }: { clip: ClipData; onChanged: () => void }) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [assets, setAssets] = useState<AssetData[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Director
  const [opts, setOpts] = useState<AiEditOptions>({
    instruction: "",
    broll_images: true,
    broll_video: false,
    voiceover: false,
    music: true,
    sfx: true,
    auto_render: true,
  });

  // Manual layer
  const [kind, setKind] = useState<AssetKind>("image");
  const [prompt, setPrompt] = useState("");
  const [start, setStart] = useState(0);
  const [length, setLength] = useState(3);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState("");

  const [origVolume, setOrigVolume] = useState(Number(clip.render_settings.original_volume ?? 1));

  const load = useCallback(() => api.listAssets(clip.id).then(setAssets).catch(() => undefined), [clip.id]);
  const loadStatus = useCallback(() => api.aiStatus().then(setStatus).catch(() => undefined), []);

  useEffect(() => {
    load();
    loadStatus();
  }, [load, loadStatus]);

  // Poll while anything is generating; refresh the job once it settles.
  const pending = assets.some((a) => a.status === "pending");
  const wasPending = useRef(false);
  useEffect(() => {
    if (pending) {
      const t = setInterval(load, 2000);
      wasPending.current = true;
      return () => clearInterval(t);
    }
    if (wasPending.current) {
      wasPending.current = false;
      onChanged();
      loadStatus();
    }
  }, [pending, load, loadStatus, onChanged]);

  const elReady = Boolean(status?.elevenlabs.configured);
  const xaiReady = Boolean(status?.xai.configured);
  const canPlan = Boolean(status?.planner);

  useEffect(() => {
    if ((kind === "voiceover" || opts.voiceover) && elReady && voices.length === 0) {
      api.voices().then(setVoices).catch(() => undefined);
    }
  }, [kind, opts.voiceover, elReady, voices.length]);

  const run = async (fn: () => Promise<unknown>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const plan = assets.find((a) => a.kind === "plan");
  const layers = assets.filter((a) => a.kind !== "plan");
  const directing = plan?.status === "pending";
  const cfg = KINDS[kind];
  const providerReady = cfg.provider === "xai" ? xaiReady : elReady;

  const estimate =
    status && kind === "image"
      ? `~$${status.rates.image_usd.toFixed(2)}`
      : status && kind === "video"
        ? `~$${(status.rates.video_usd_per_sec * Math.max(1, Math.round(length))).toFixed(2)}`
        : kind === "voiceover"
          ? `${prompt.length} credits`
          : "";

  const patch = (a: AssetData, body: Parameters<typeof api.updateAsset>[1]) =>
    run(async () => {
      await api.updateAsset(a.id, body);
      onChanged();
    });

  return (
    <div className="space-y-4 rounded-xl border border-primary/30 bg-surface-2/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-bold">
          <Sparkles className="h-4 w-4 text-primary" />
          AI Studio
        </p>
        {status && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={xaiReady ? "success" : "muted"}>
              Grok {xaiReady ? `· ~$${status.usage.xai_est_usd.toFixed(2)}${status.usage.budget_usd > 0 ? ` / $${status.usage.budget_usd.toFixed(2)}` : ""} used` : "· no key"}
            </Badge>
            <Badge tone={elReady ? "success" : "muted"}>
              ElevenLabs{" "}
              {elReady
                ? status.elevenlabs.credits
                  ? `· ${status.elevenlabs.credits.remaining.toLocaleString()} credits left`
                  : "· connected"
                : "· no key"}
            </Badge>
          </div>
        )}
      </div>

      {status && (!xaiReady || !elReady) && (
        <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          {!xaiReady && !elReady
            ? "Add your Grok (xAI) and ElevenLabs API keys to generate B-roll, voiceover, music and sound effects."
            : !xaiReady
              ? "Add a Grok (xAI) API key to generate B-roll images and video."
              : "Add an ElevenLabs API key for voiceover, music and sound effects."}{" "}
          <Link href="/settings" className="font-semibold underline">
            Open AI settings
          </Link>
        </p>
      )}

      {error && <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}

      {/* Director */}
      <div className="space-y-2.5 rounded-lg border border-border bg-surface p-3">
        <Label className="mb-0">AI edit — describe what you want</Label>
        <textarea
          rows={2}
          value={opts.instruction}
          onChange={(e) => setOpts({ ...opts, instruction: e.target.value })}
          placeholder="e.g. Make it punchy and dramatic, add B-roll for every example, energetic music"
          className={textareaClass}
        />
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          <Switch checked={opts.broll_images} onChange={(v) => setOpts({ ...opts, broll_images: v })} label="B-roll images" />
          <Switch checked={opts.broll_video} onChange={(v) => setOpts({ ...opts, broll_video: v })} label="B-roll video" />
          <Switch checked={opts.music} onChange={(v) => setOpts({ ...opts, music: v })} label="Music" />
          <Switch checked={opts.sfx} onChange={(v) => setOpts({ ...opts, sfx: v })} label="Sound effects" />
          <Switch checked={opts.voiceover} onChange={(v) => setOpts({ ...opts, voiceover: v })} label="Voiceover" />
          <Switch checked={opts.auto_render} onChange={(v) => setOpts({ ...opts, auto_render: v })} label="Render when done" />
        </div>
        {opts.voiceover && voices.length > 0 && (
          <Select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} className="sm:w-72">
            <option value="">Default voice</option>
            {voices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}>
                {v.name}
                {v.description ? ` — ${v.description}` : ""}
              </option>
            ))}
          </Select>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={!canPlan || busy || directing}
            onClick={() => run(() => api.aiEdit(clip.id, { ...opts, voice_id: voiceId || undefined }))}
          >
            {directing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
            {directing ? (plan?.meta.stage === "generating" ? "Generating layers…" : "Planning the edit…") : "Edit with AI"}
          </Button>
          <span className="text-[11px] text-muted">
            {status?.planner === "anthropic" ? "Claude" : "Grok"} plans the edit; video B-roll is the slowest and most
            expensive option.
            {!xaiReady && " B-roll is skipped until a Grok key is added."}
            {!elReady && " Audio options are skipped until an ElevenLabs key is added."}
          </span>
        </div>
        {plan && plan.status !== "pending" && (
          <div className="flex items-start justify-between gap-2 text-xs">
            {plan.status === "failed" ? (
              <p className="text-danger">AI edit failed: {plan.error}</p>
            ) : (
              <p className="text-muted">
                <span className="font-semibold text-foreground">Last AI edit:</span> {plan.meta.plan?.notes || "applied."}{" "}
                {plan.meta.generated ?? 0} layer(s) generated
                {plan.meta.failed ? `, ${plan.meta.failed} failed` : ""}.
              </p>
            )}
            <button
              className="shrink-0 cursor-pointer text-muted hover:text-foreground"
              onClick={() => run(() => api.deleteAsset(plan.id))}
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Manual layer */}
      <div className="space-y-2.5 rounded-lg border border-border bg-surface p-3">
        <Label className="mb-0">Generate a single layer</Label>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(KINDS) as AssetKind[]).map((k) => {
            const Icon = KINDS[k].icon;
            return (
              <button
                key={k}
                onClick={() => {
                  setKind(k);
                  setLength(k === "video" ? 6 : 3);
                }}
                className={cn(
                  "flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition",
                  kind === k ? "border-primary bg-primary/15 text-primary" : "border-border text-muted hover:text-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {KINDS[k].label}
              </button>
            );
          })}
        </div>
        <textarea
          rows={kind === "voiceover" ? 3 : 2}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={cfg.placeholder}
          className={textareaClass}
        />
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[11px] text-muted">
            Starts at (s)
            <Input
              type="number"
              min={0}
              max={clip.duration}
              step={0.1}
              value={start}
              onChange={(e) => setStart(Number(e.target.value))}
              className="mt-1 h-8 w-24 text-xs"
            />
          </label>
          {(kind === "image" || kind === "video") && (
            <label className="text-[11px] text-muted">
              Length (s)
              <Input
                type="number"
                min={1}
                max={kind === "video" ? 15 : clip.duration}
                step={0.5}
                value={length}
                onChange={(e) => setLength(Number(e.target.value))}
                className="mt-1 h-8 w-24 text-xs"
              />
            </label>
          )}
          {kind === "voiceover" && voices.length > 0 && (
            <label className="text-[11px] text-muted">
              Voice
              <Select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} className="mt-1 h-8 w-52 text-xs">
                <option value="">Default voice</option>
                {voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </label>
          )}
          <Button
            size="sm"
            disabled={!providerReady || busy || !prompt.trim()}
            onClick={() =>
              run(async () => {
                await api.createAsset(clip.id, {
                  kind,
                  prompt,
                  start,
                  end: kind === "image" || kind === "video" ? start + length : undefined,
                  voice_id: kind === "voiceover" && voiceId ? voiceId : undefined,
                });
                setPrompt("");
              })
            }
          >
            <Sparkles className="h-3.5 w-3.5" />
            Generate
          </Button>
          {estimate && <span className="pb-1.5 text-[11px] text-muted">{estimate}</span>}
        </div>
      </div>

      {/* Layers */}
      {layers.length > 0 && (
        <div className="space-y-2">
          <Label className="mb-0">Layers on this clip</Label>
          {layers.map((a) => {
            const Icon = KINDS[a.kind as AssetKind]?.icon ?? Sparkles;
            return (
              <div
                key={a.id}
                className={cn("space-y-2 rounded-lg border border-border bg-surface p-2.5", !a.enabled && "opacity-60")}
              >
                <div className="flex items-start gap-2.5">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-2">
                    {a.status === "pending" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    ) : a.file_url && a.kind === "image" ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={a.file_url} alt={a.prompt} className="h-full w-full object-cover" />
                    ) : a.file_url && a.kind === "video" ? (
                      <video src={a.file_url} muted loop autoPlay playsInline className="h-full w-full object-cover" />
                    ) : (
                      <Icon className="h-4 w-4 text-muted" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-xs font-semibold">
                      {KINDS[a.kind as AssetKind]?.label ?? a.kind}
                      <Badge tone={a.status === "ready" ? "success" : a.status === "failed" ? "danger" : "info"}>
                        {a.status === "pending" ? "generating" : a.status}
                      </Badge>
                    </p>
                    <p className="line-clamp-2 text-[11.5px] text-muted">{a.prompt}</p>
                    {a.error && <p className="text-[11.5px] text-danger">{a.error}</p>}
                  </div>
                  <Button variant="ghost" size="icon" title="Delete layer" onClick={() => run(async () => { await api.deleteAsset(a.id); onChanged(); })}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                {a.status === "ready" && (
                  <div className="flex flex-wrap items-center gap-3">
                    {isAudio(a.kind) && a.file_url && <audio src={a.file_url} controls className="h-8 w-48" />}
                    <NumberField label="start s" value={a.start} max={clip.duration} onCommit={(v) => patch(a, { start: v })} />
                    <NumberField label="end s" value={a.end} max={clip.duration} onCommit={(v) => patch(a, { end: v })} />
                    {isAudio(a.kind) && (
                      <NumberField label="volume" value={a.volume} max={2} step={0.05} onCommit={(v) => patch(a, { volume: v })} />
                    )}
                    <Switch checked={a.enabled} onChange={(v) => patch(a, { enabled: v })} label="Use" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
        <label className="flex items-center gap-2 text-[11px] text-muted">
          Original audio
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={origVolume}
            onChange={(e) => setOrigVolume(Number(e.target.value))}
            onMouseUp={() => run(() => api.updateClip(clip.id, { render_settings: { original_volume: origVolume } }).then(onChanged))}
            onTouchEnd={() => run(() => api.updateClip(clip.id, { render_settings: { original_volume: origVolume } }).then(onChanged))}
            className="w-28"
          />
          {Math.round(origVolume * 100)}%
        </label>
        <Button
          variant="secondary"
          size="sm"
          disabled={busy || pending || clip.render_status === "rendering"}
          onClick={() => run(() => api.renderClip(clip.id).then(onChanged))}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Render with layers
        </Button>
        {clip.has_output && clip.render_status === "detected" && (
          <span className="text-[11px] text-warning">Layers changed — render again to see them.</span>
        )}
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  max,
  step = 0.1,
  onCommit,
}: {
  label: string;
  value: number;
  max: number;
  step?: number;
  onCommit: (v: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    const v = Number(draft);
    if (Number.isFinite(v) && v !== value) onCommit(Math.max(0, Math.min(max, v)));
    else setDraft(String(value));
  };
  return (
    <label className="flex items-center gap-1 text-[10px] text-muted">
      <Input
        type="number"
        min={0}
        max={max}
        step={step}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        className="h-8 w-20 text-xs"
      />
      {label}
    </label>
  );
}
