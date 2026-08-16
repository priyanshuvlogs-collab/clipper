"use client";

import { useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Captions,
  Download,
  Flame,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Type,
  X,
} from "lucide-react";
import { api, type ClipData, type Overlay } from "@/lib/api";
import { cn, formatTime, formatTimePrecise } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";

const EMOJIS = ["🔥", "😱", "💰", "🚀", "⚡", "❤️", "💯", "👀", "🎯", "😂"];

function scoreTone(score: number): "success" | "warning" | "muted" {
  if (score >= 60) return "success";
  if (score >= 40) return "warning";
  return "muted";
}

export function ClipCard({
  clip,
  index,
  total,
  sourceDuration,
  selected,
  checked,
  onCheck,
  onChanged,
  onMove,
}: {
  clip: ClipData;
  index: number;
  total: number;
  sourceDuration: number;
  selected: boolean;
  checked: boolean;
  onCheck: (v: boolean) => void;
  onChanged: () => void;
  onMove: (dir: -1 | 1) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState(clip.start);
  const [end, setEnd] = useState(clip.end);
  const [title, setTitle] = useState(clip.title);
  const [overlays, setOverlays] = useState<Overlay[]>(clip.overlays);
  const [burnSubs, setBurnSubs] = useState(Boolean(clip.render_settings.burn_subtitles ?? true));
  const [kenBurns, setKenBurns] = useState(Boolean(clip.render_settings.ken_burns ?? true));
  const [aspect, setAspect] = useState(String(clip.render_settings.aspect ?? "9:16"));
  const [saving, setSaving] = useState(false);

  const rendering = clip.render_status === "rendering";

  const save = async (thenRender: boolean) => {
    setSaving(true);
    try {
      await api.updateClip(clip.id, {
        start,
        end,
        title,
        overlays,
        render_settings: { burn_subtitles: burnSubs, ken_burns: kenBurns, aspect },
      });
      if (thenRender) await api.renderClip(clip.id);
      setEditing(false);
      onChanged();
    } finally {
      setSaving(false);
    }
  };

  const nudge = (which: "start" | "end", delta: number) => {
    if (which === "start") setStart((s) => Math.max(0, Math.min(end - 1, +(s + delta).toFixed(2))));
    else setEnd((e) => Math.min(sourceDuration || e + delta, Math.max(start + 1, +(e + delta).toFixed(2))));
  };

  const addOverlay = (emoji?: string) =>
    setOverlays((o) => [
      ...o,
      { text: emoji ?? "Your text", start: 0, end: Math.min(3, end - start), x: 50, y: emoji ? 12 : 18, size: emoji ? 96 : 56, color: "white" },
    ]);

  return (
    <Card id={`clip-${clip.id}`} className={cn("overflow-hidden transition", selected && "border-accent ring-2 ring-accent/40")}>
      <div className="flex flex-col gap-4 p-4 sm:flex-row">
        {/* Preview */}
        <div className="w-full shrink-0 sm:w-44">
          {clip.has_output && clip.preview_url ? (
            <video
              key={clip.preview_url + String(clip.render_progress)}
              src={clip.preview_url}
              controls
              playsInline
              className={cn(
                "w-full rounded-lg border border-border bg-black",
                aspect === "9:16" ? "aspect-[9/16]" : aspect === "1:1" ? "aspect-square" : "aspect-video",
              )}
            />
          ) : (
            <div
              className={cn(
                "flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 p-3 text-center",
                aspect === "9:16" ? "aspect-[9/16]" : aspect === "1:1" ? "aspect-square" : "aspect-video",
              )}
            >
              {rendering ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <p className="text-[11px] font-semibold text-muted">Rendering… {Math.round(clip.render_progress)}%</p>
                  <Progress value={clip.render_progress} className="w-full" />
                </>
              ) : clip.render_status === "failed" ? (
                <p className="text-[11px] text-danger">Render failed</p>
              ) : (
                <p className="text-[11px] text-muted">Not rendered yet</p>
              )}
            </div>
          )}
        </div>

        {/* Body */}
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-start gap-2.5">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onCheck(e.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-[var(--primary)]"
                title="Select for merge"
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-bold">
                  <span className="mr-1.5 text-muted">#{index + 1}</span>
                  {clip.title || "Untitled clip"}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {formatTime(clip.start)} – {formatTime(clip.end)} · {clip.duration.toFixed(1)}s
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Badge tone={scoreTone(clip.score)}>
                <Flame className="h-3 w-3" />
                {clip.score.toFixed(0)}
              </Badge>
              <Button variant="ghost" size="icon" disabled={index === 0} onClick={() => onMove(-1)} title="Move up">
                <ArrowUp className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" disabled={index === total - 1} onClick={() => onMove(1)} title="Move down">
                <ArrowDown className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {clip.hook_text && (
            <p className="line-clamp-2 rounded-lg border border-border bg-surface-2/60 px-3 py-2 text-[12.5px] italic leading-relaxed text-muted">
              “{clip.hook_text.trim()}”
            </p>
          )}

          {/* Score breakdown */}
          <div className="flex flex-wrap gap-1.5 text-[10.5px]">
            {Object.entries(clip.score_breakdown)
              .filter(([k]) => k !== "merged_from")
              .map(([k, v]) => (
                <span key={k} className="rounded-full border border-border bg-surface-2 px-2 py-0.5 text-muted">
                  {k.replace(/_/g, " ")}: <span className="font-semibold text-foreground">{typeof v === "number" ? v.toFixed(2) : v}</span>
                </span>
              ))}
          </div>

          {clip.render_error && <p className="text-xs text-danger">{clip.render_error}</p>}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditing((v) => !v)}>
              <Pencil className="h-3.5 w-3.5" />
              {editing ? "Close editor" : "Edit"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={rendering}
              onClick={() => api.renderClip(clip.id).then(onChanged)}
            >
              {rendering ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {clip.has_output ? "Re-render" : "Render"}
            </Button>
            {clip.download_url && (
              <a href={clip.download_url}>
                <Button size="sm">
                  <Download className="h-3.5 w-3.5" />
                  MP4
                </Button>
              </a>
            )}
            {clip.srt_url && (
              <a href={clip.srt_url}>
                <Button variant="outline" size="sm">
                  <Captions className="h-3.5 w-3.5" />
                  SRT
                </Button>
              </a>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (confirm("Delete this clip?")) api.deleteClip(clip.id).then(onChanged);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Editor */}
          {editing && (
            <div className="space-y-4 rounded-xl border border-border bg-surface-2/60 p-4">
              <div>
                <Label>Title</Label>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>

              <div className="grid grid-cols-2 gap-4">
                {(
                  [
                    ["start", start, setStart],
                    ["end", end, setEnd],
                  ] as const
                ).map(([which, value, setter]) => (
                  <div key={which}>
                    <Label>{which === "start" ? "Start" : "End"} — {formatTimePrecise(value)}</Label>
                    <div className="flex items-center gap-1.5">
                      <Button variant="outline" size="sm" onClick={() => nudge(which, -1)}>-1s</Button>
                      <Button variant="outline" size="sm" onClick={() => nudge(which, -0.1)}>-0.1</Button>
                      <Input
                        type="number"
                        step={0.1}
                        value={value}
                        onChange={(e) => setter(Number(e.target.value))}
                        className="text-center"
                      />
                      <Button variant="outline" size="sm" onClick={() => nudge(which, 0.1)}>+0.1</Button>
                      <Button variant="outline" size="sm" onClick={() => nudge(which, 1)}>+1s</Button>
                    </div>
                  </div>
                ))}
              </div>

              <input
                type="range"
                min={0}
                max={sourceDuration || end}
                step={0.1}
                value={start}
                onChange={(e) => setStart(Math.min(Number(e.target.value), end - 1))}
                className="w-full"
              />

              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div>
                  <Label>Format</Label>
                  <Select value={aspect} onChange={(e) => setAspect(e.target.value)}>
                    <option value="9:16">9:16 vertical</option>
                    <option value="16:9">16:9 horizontal</option>
                    <option value="1:1">1:1 square</option>
                  </Select>
                </div>
                <div className="flex items-end gap-4 pb-1 sm:col-span-2">
                  <Switch checked={burnSubs} onChange={setBurnSubs} label="Burn captions" />
                  <Switch checked={kenBurns} onChange={setKenBurns} label="Ken Burns" />
                </div>
              </div>

              {/* Overlays */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="mb-0">Text &amp; emoji overlays</Label>
                  <div className="flex items-center gap-1">
                    {EMOJIS.slice(0, 5).map((e) => (
                      <button
                        key={e}
                        onClick={() => addOverlay(e)}
                        className="cursor-pointer rounded-md border border-border bg-surface px-1.5 py-0.5 text-sm transition hover:border-primary"
                        title={`Add ${e} overlay`}
                      >
                        {e}
                      </button>
                    ))}
                    <Button variant="outline" size="sm" onClick={() => addOverlay()}>
                      <Plus className="h-3 w-3" />
                      <Type className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
                {overlays.map((ov, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-2">
                    <Input
                      value={ov.text}
                      onChange={(e) =>
                        setOverlays((o) => o.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
                      }
                      className="h-8 flex-1 text-xs"
                      placeholder="Overlay text / emoji"
                    />
                    {(
                      [
                        ["start", "s", 0, end - start],
                        ["end", "e", 0, end - start],
                        ["y", "y%", 0, 100],
                        ["size", "px", 16, 200],
                      ] as const
                    ).map(([key, suffix, min, max]) => (
                      <label key={key} className="flex items-center gap-1 text-[10px] text-muted">
                        <Input
                          type="number"
                          min={min}
                          max={max}
                          value={ov[key]}
                          onChange={(e) =>
                            setOverlays((o) =>
                              o.map((x, j) => (j === i ? { ...x, [key]: Number(e.target.value) } : x)),
                            )
                          }
                          className="h-8 w-16 text-xs"
                        />
                        {suffix}
                      </label>
                    ))}
                    <Button variant="ghost" size="icon" onClick={() => setOverlays((o) => o.filter((_, j) => j !== i))}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="flex gap-2">
                <Button size="sm" disabled={saving} onClick={() => save(true)}>
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Save &amp; render
                </Button>
                <Button variant="secondary" size="sm" disabled={saving} onClick={() => save(false)}>
                  Save only
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
