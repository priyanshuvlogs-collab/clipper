"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Combine,
  Download,
  FileText,
  Languages,
  Loader2,
  XCircle,
} from "lucide-react";
import { api, type JobDetail } from "@/lib/api";
import { formatTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ClipCard } from "@/components/clip-card";
import { Timeline } from "@/components/timeline";

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting in queue…",
  downloading: "Downloading source video…",
  probing: "Analyzing video…",
  extracting_audio: "Extracting audio track…",
  transcribing: "Transcribing speech…",
  detecting: "Scoring the best moments…",
  rendering: "Rendering clips…",
};

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [selectedClip, setSelectedClip] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [showTranscript, setShowTranscript] = useState(false);
  const [merging, setMerging] = useState(false);

  const refresh = useCallback(() => {
    api
      .getJob(id)
      .then(setJob)
      .catch(() => setNotFound(true));
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll faster while work is in flight.
  const busy =
    job?.status === "running" ||
    job?.status === "queued" ||
    job?.clips.some((c) => c.render_status === "rendering");

  useEffect(() => {
    const t = setInterval(refresh, busy ? 1500 : 6000);
    return () => clearInterval(t);
  }, [refresh, busy]);

  const orderedClips = useMemo(
    () => (job ? [...job.clips].sort((a, b) => a.order_index - b.order_index) : []),
    [job],
  );

  const move = async (clipId: string, dir: -1 | 1) => {
    const ids = orderedClips.map((c) => c.id);
    const i = ids.indexOf(clipId);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await api.reorderClips(id, ids);
    refresh();
  };

  const merge = async () => {
    const ids = orderedClips.filter((c) => checked.has(c.id)).map((c) => c.id);
    if (ids.length < 2) return;
    setMerging(true);
    try {
      await api.mergeClips(id, ids, "Merged clip");
      setChecked(new Set());
      refresh();
    } finally {
      setMerging(false);
    }
  };

  if (notFound) {
    return (
      <div className="py-20 text-center">
        <XCircle className="mx-auto h-10 w-10 text-danger" />
        <p className="mt-3 font-semibold">Job not found</p>
        <Link href="/" className="mt-2 inline-block text-sm text-primary hover:underline">
          Back to dashboard
        </Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/" className="mb-1 inline-flex items-center gap-1 text-xs text-muted transition hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" /> Dashboard
          </Link>
          <h1 className="truncate text-xl font-bold tracking-tight">{job.title || job.source}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
            {job.duration > 0 && <Badge tone="muted">{formatTime(job.duration)}</Badge>}
            {job.language && (
              <Badge tone="info">
                <Languages className="h-3 w-3" />
                {job.language.toUpperCase()}
                {job.language_probability > 0 && ` ${(job.language_probability * 100).toFixed(0)}%`}
              </Badge>
            )}
            {job.transcription_engine && <Badge tone="muted">engine: {job.transcription_engine}</Badge>}
            {job.width > 0 && <Badge tone="muted">{job.width}×{job.height}</Badge>}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {job.txt_url && (
            <Button variant="secondary" size="sm" onClick={() => setShowTranscript((v) => !v)}>
              <FileText className="h-3.5 w-3.5" />
              Transcript
            </Button>
          )}
          {job.srt_url && (
            <a href={job.srt_url}>
              <Button variant="outline" size="sm">SRT</Button>
            </a>
          )}
          {job.vtt_url && (
            <a href={job.vtt_url}>
              <Button variant="outline" size="sm">VTT</Button>
            </a>
          )}
          {job.txt_url && (
            <a href={job.txt_url}>
              <Button variant="outline" size="sm">TXT</Button>
            </a>
          )}
          {job.clip_count > 0 && (
            <a href={`/api/jobs/${job.id}/download-all`}>
              <Button size="sm">
                <Download className="h-3.5 w-3.5" />
                Download all
              </Button>
            </a>
          )}
        </div>
      </div>

      {/* Progress */}
      {(job.status === "running" || job.status === "queued") && (
        <Card>
          <CardContent className="space-y-2 p-5">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-semibold">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                {STAGE_LABELS[job.stage] ?? job.stage}
              </span>
              <span className="font-mono text-muted">{job.progress.toFixed(0)}%</span>
            </div>
            <Progress value={job.progress} />
          </CardContent>
        </Card>
      )}

      {job.status === "failed" && (
        <Card className="border-danger/40">
          <CardContent className="p-5">
            <p className="flex items-center gap-2 text-sm font-semibold text-danger">
              <XCircle className="h-4 w-4" /> Processing failed
            </p>
            <p className="mt-1.5 break-words font-mono text-xs text-muted">{job.error}</p>
          </CardContent>
        </Card>
      )}

      {/* Transcript */}
      {showTranscript && job.segments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Transcript</CardTitle>
          </CardHeader>
          <CardContent className="max-h-80 space-y-1.5 overflow-y-auto">
            {job.segments.map((seg, i) => (
              <p key={i} className="text-[13px] leading-relaxed">
                <span className="mr-2 font-mono text-[11px] text-muted">{formatTime(seg.start)}</span>
                {seg.text}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Timeline */}
      {orderedClips.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Timeline · {orderedClips.length} clips</CardTitle>
            <Button variant="secondary" size="sm" disabled={checked.size < 2 || merging} onClick={merge}>
              {merging ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Combine className="h-3.5 w-3.5" />}
              Merge selected ({checked.size})
            </Button>
          </CardHeader>
          <CardContent>
            <Timeline
              duration={job.duration}
              clips={orderedClips}
              selectedId={selectedClip}
              onSelect={(cid) => {
                setSelectedClip(cid);
                document.getElementById(`clip-${cid}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            />
          </CardContent>
        </Card>
      )}

      {/* Clips */}
      <div className="space-y-4">
        {orderedClips.map((clip, i) => (
          <ClipCard
            key={clip.id}
            clip={clip}
            index={i}
            total={orderedClips.length}
            sourceDuration={job.duration}
            selected={selectedClip === clip.id}
            checked={checked.has(clip.id)}
            onCheck={(v) =>
              setChecked((prev) => {
                const next = new Set(prev);
                if (v) next.add(clip.id);
                else next.delete(clip.id);
                return next;
              })
            }
            onChanged={refresh}
            onMove={(dir) => move(clip.id, dir)}
          />
        ))}
      </div>

      {job.status === "completed" && orderedClips.length === 0 && (
        <Card className="border-dashed p-10 text-center text-sm text-muted">
          No clips were detected — the video may be too short or have no speech.
        </Card>
      )}
    </div>
  );
}
