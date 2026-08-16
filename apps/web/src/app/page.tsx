"use client";

import { useCallback, useEffect, useState } from "react";
import { Captions, Scissors, Wand2 } from "lucide-react";
import { api, type JobSummary } from "@/lib/api";
import { CreateJob } from "@/components/create-job";
import { JobList } from "@/components/job-list";

const FEATURES = [
  {
    icon: Captions,
    title: "Multilingual transcription",
    text: "Faster-Whisper locally with Groq / Deepgram / AssemblyAI fallbacks. Hindi, English and 90+ languages with word-level timestamps.",
  },
  {
    icon: Wand2,
    title: "Smart moment detection",
    text: "Hooks, speech energy, keyword salience and silence analysis rank the highest-retention moments automatically.",
  },
  {
    icon: Scissors,
    title: "Studio-grade rendering",
    text: "1080p vertical clips with burned-in animated captions, subtle Ken Burns zoom, music beds and text overlays.",
  },
];

export default function HomePage() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);

  const refresh = useCallback(() => {
    api.listJobs().then(setJobs).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="space-y-10">
      <section className="pt-4 text-center">
        <h1 className="mx-auto max-w-2xl bg-gradient-to-br from-white via-white to-primary bg-clip-text text-4xl font-extrabold tracking-tight text-transparent md:text-5xl">
          Turn long videos into viral clips
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-muted">
          AI transcription, smart highlight detection and professional 9:16 rendering — Shorts,
          Reels and TikToks in one click.
        </p>
      </section>

      <CreateJob onCreated={refresh} />

      <section className="grid gap-4 md:grid-cols-3">
        {FEATURES.map((f) => (
          <div key={f.title} className="rounded-xl border border-border bg-surface/60 p-5">
            <f.icon className="h-5 w-5 text-accent" />
            <h3 className="mt-3 text-sm font-bold">{f.title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{f.text}</p>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-bold tracking-tight">Recent jobs</h2>
        <JobList jobs={jobs} onDeleted={refresh} />
      </section>
    </div>
  );
}
