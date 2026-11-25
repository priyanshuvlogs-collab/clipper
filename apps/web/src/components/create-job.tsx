"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, CloudUpload, Link2, Loader2, Sparkles } from "lucide-react";
import { api, DEFAULT_PARAMS, type EngineInfo, type JobParams } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const LANGUAGES = [
  ["auto", "Auto-detect"],
  ["en", "English"],
  ["hi", "Hindi (हिन्दी)"],
  ["es", "Spanish"],
  ["fr", "French"],
  ["de", "German"],
  ["pt", "Portuguese"],
  ["ja", "Japanese"],
  ["ko", "Korean"],
  ["ar", "Arabic"],
  ["ru", "Russian"],
  ["ta", "Tamil"],
  ["te", "Telugu"],
  ["bn", "Bengali"],
  ["ur", "Urdu"],
] as const;

export function CreateJob({ onCreated }: { onCreated?: () => void }) {
  const router = useRouter();
  const [tab, setTab] = useState<"upload" | "link">("upload");
  const [params, setParams] = useState<JobParams>(DEFAULT_PARAMS);
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [showMore, setShowMore] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.engines().then(setEngines).catch(() => {});
  }, []);

  const set = <K extends keyof JobParams>(key: K, value: JobParams[K]) =>
    setParams((p) => ({ ...p, [key]: value }));

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) {
      setFile(f);
      setTab("upload");
    }
  }, []);

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      const job =
        tab === "link"
          ? await api.createUrlJob(url.trim(), params)
          : file
            ? await api.uploadJob(file, params)
            : null;
      if (!job) {
        setError("Choose a video file first.");
        return;
      }
      onCreated?.();
      router.push(`/jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const ready = tab === "link" ? url.trim().length > 8 : file !== null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          Make clips from a video
        </CardTitle>
        <CardDescription>
          Add a long video. You get back short clips of its best moments, with captions, ready to
          download.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Source tabs */}
        <div className="flex gap-1 rounded-lg border border-border bg-surface-2 p-1">
          {(
            [
              ["upload", "Upload file", CloudUpload],
              ["link", "YouTube / URL", Link2],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-md py-2 text-[13px] font-semibold transition",
                tab === id ? "bg-primary text-white shadow" : "text-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>

        {tab === "upload" ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInput.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
              dragging
                ? "border-primary bg-primary/10"
                : "border-border bg-surface-2/50 hover:border-primary/50 hover:bg-surface-2",
            )}
          >
            <CloudUpload className="h-8 w-8 text-primary" />
            {file ? (
              <>
                <p className="text-sm font-semibold">{file.name}</p>
                <p className="text-xs text-muted">{(file.size / 1024 / 1024).toFixed(1)} MB — click to change</p>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold">Drag &amp; drop your video here</p>
                <p className="text-xs text-muted">MP4, MOV, MKV or WebM — or click to browse</p>
              </>
            )}
            <input
              ref={fileInput}
              type="file"
              accept=".mp4,.mov,.mkv,.webm,.m4v,video/*"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        ) : (
          <div>
            <Label>Video link</Label>
            <div className="relative">
              <Link2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…  or a direct .mp4 URL"
                className="pl-9"
              />
            </div>
            <p className="mt-1.5 text-xs text-muted">
              Supports YouTube, YouTube Shorts, and direct video URLs.
            </p>
          </div>
        )}

        {/* Basics */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <Label>Spoken language</Label>
            <Select value={params.language} onChange={(e) => set("language", e.target.value)}>
              {LANGUAGES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>How many clips</Label>
            <Input
              type="number"
              min={1}
              max={20}
              value={params.num_clips}
              onChange={(e) => set("num_clips", Number(e.target.value) || 1)}
            />
          </div>
          <div>
            <Label>Shape</Label>
            <Select
              value={params.aspect}
              onChange={(e) => set("aspect", e.target.value as JobParams["aspect"])}
            >
              <option value="9:16">Vertical — Shorts, Reels, TikTok</option>
              <option value="16:9">Wide — YouTube</option>
              <option value="1:1">Square — feed posts</option>
            </Select>
          </div>
        </div>

        {/* Advanced */}
        <div>
          <button
            type="button"
            aria-expanded={showMore}
            onClick={() => setShowMore((v) => !v)}
            className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-muted transition hover:text-foreground"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", showMore && "rotate-180")} />
            More options
          </button>
          {showMore && (
            <div className="mt-4 space-y-4 rounded-xl border border-border bg-surface-2/50 p-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <Label>Shortest clip (seconds)</Label>
                  <Input
                    type="number"
                    min={3}
                    value={params.min_duration}
                    onChange={(e) => set("min_duration", Number(e.target.value) || 15)}
                  />
                </div>
                <div>
                  <Label>Longest clip (seconds)</Label>
                  <Input
                    type="number"
                    min={5}
                    value={params.max_duration}
                    onChange={(e) => set("max_duration", Number(e.target.value) || 60)}
                  />
                </div>
                <div>
                  <Label>Transcription engine</Label>
                  <Select value={params.engine} onChange={(e) => set("engine", e.target.value)}>
                    <option value="auto">Automatic (recommended)</option>
                    {engines.map((e) => (
                      <option key={e.id} value={e.id} disabled={!e.available}>
                        {e.name}
                        {!e.available ? " — not set up" : ""}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-3">
                <Switch checked={params.burn_subtitles} onChange={(v) => set("burn_subtitles", v)} label="Captions on the video" />
                <Switch checked={params.ken_burns} onChange={(v) => set("ken_burns", v)} label="Slow zoom" />
                <Switch checked={params.remove_silence} onChange={(v) => set("remove_silence", v)} label="Cut out silences" />
              </div>
              {engines.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  <span className="mr-1 font-semibold">Engines available:</span>
                  {engines.map((e) => (
                    <Badge key={e.id} tone={e.available ? "success" : "muted"} title={e.detail}>
                      {e.name.split(" (")[0]}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
            {error}
          </p>
        )}

        <Button size="lg" className="w-full" disabled={!ready || busy} onClick={submit}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "Starting…" : ready ? "Generate clips" : tab === "link" ? "Paste a link to start" : "Choose a video to start"}
        </Button>
      </CardContent>
    </Card>
  );
}
