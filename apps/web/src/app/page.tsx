"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkles, Upload, Wand2 } from "lucide-react";
import { api, type JobSummary } from "@/lib/api";
import { CreateJob } from "@/components/create-job";
import { JobList } from "@/components/job-list";
import { SetupGuide } from "@/components/setup-guide";

const STEPS = [
  {
    icon: Upload,
    title: "1. Add a video",
    text: "Upload a file or paste a YouTube link. Long podcasts, interviews and streams work best.",
  },
  {
    icon: Wand2,
    title: "2. We find the best moments",
    text: "The video is transcribed (Hindi, English and 90+ languages) and the strongest moments are cut into captioned clips.",
  },
  {
    icon: Sparkles,
    title: "3. Polish and download",
    text: "Trim, add text, or open AI Studio for B-roll, music and voiceover. Then download and post.",
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
          Add a video and get ready-to-post Shorts, Reels and TikToks with captions — no editing
          skills needed.
        </p>
      </section>

      <CreateJob onCreated={refresh} />

      <section className="grid gap-4 md:grid-cols-3" aria-label="How it works">
        {STEPS.map((f) => (
          <div key={f.title} className="rounded-xl border border-border bg-surface/60 p-5">
            <f.icon className="h-5 w-5 text-accent" />
            <h3 className="mt-3 text-sm font-bold">{f.title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{f.text}</p>
          </div>
        ))}
      </section>

      <SetupGuide />

      <section className="space-y-3">
        <h2 className="text-lg font-bold tracking-tight">Your videos</h2>
        <JobList jobs={jobs} onDeleted={refresh} />
      </section>
    </div>
  );
}
