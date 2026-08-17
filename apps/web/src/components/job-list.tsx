"use client";

import Link from "next/link";
import { CheckCircle2, Clock, Film, Link2, Loader2, Trash2, XCircle } from "lucide-react";
import { api, type JobSummary } from "@/lib/api";
import { formatTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  downloading: "Downloading source",
  probing: "Analyzing video",
  extracting_audio: "Extracting audio",
  transcribing: "Transcribing",
  detecting: "Finding best moments",
  rendering: "Rendering clips",
  completed: "Completed",
  failed: "Failed",
};

function StatusBadge({ job }: { job: JobSummary }) {
  if (job.status === "completed")
    return (
      <Badge tone="success">
        <CheckCircle2 className="h-3 w-3" /> Done
      </Badge>
    );
  if (job.status === "failed")
    return (
      <Badge tone="danger">
        <XCircle className="h-3 w-3" /> Failed
      </Badge>
    );
  if (job.status === "running")
    return (
      <Badge tone="default">
        <Loader2 className="h-3 w-3 animate-spin" /> {STAGE_LABELS[job.stage] ?? job.stage}
      </Badge>
    );
  return (
    <Badge tone="muted">
      <Clock className="h-3 w-3" /> Queued
    </Badge>
  );
}

export function JobList({ jobs, onDeleted }: { jobs: JobSummary[]; onDeleted: () => void }) {
  if (jobs.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-2 border-dashed px-6 py-12 text-center">
        <Film className="h-8 w-8 text-muted" />
        <p className="text-sm font-semibold">No jobs yet</p>
        <p className="text-[13px] text-muted">Your processed videos and clips will show up here.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <Card key={job.id} className="transition hover:border-primary/40">
          <Link href={`/jobs/${job.id}`} className="block p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-2">
                  {job.source_type === "youtube" ? (
                    <Link2 className="h-4.5 w-4.5 text-danger" />
                  ) : (
                    <Film className="h-4.5 w-4.5 text-primary" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{job.title || job.source}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    {job.duration > 0 && <span>{formatTime(job.duration)}</span>}
                    {job.language && <span className="uppercase">{job.language}</span>}
                    {job.clip_count > 0 && <span>{job.clip_count} clips</span>}
                    <span>{new Date(job.created_at).toLocaleString()}</span>
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StatusBadge job={job} />
                <Button
                  variant="ghost"
                  size="icon"
                  title="Delete job"
                  onClick={(e) => {
                    e.preventDefault();
                    if (confirm("Delete this job and all its clips?")) {
                      api.deleteJob(job.id).then(onDeleted);
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {(job.status === "running" || job.status === "queued") && (
              <Progress value={job.progress} className="mt-3" />
            )}
            {job.status === "failed" && job.error && (
              <p className="mt-2 line-clamp-2 text-xs text-danger">{job.error}</p>
            )}
          </Link>
        </Card>
      ))}
    </div>
  );
}
