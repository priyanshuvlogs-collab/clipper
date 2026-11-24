"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, X } from "lucide-react";
import { api, type AiStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const DISMISS_KEY = "proclipper.setup-dismissed";

/** Dashboard card: what works already and which optional keys unlock more. */
export function SetupGuide() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(DISMISS_KEY) === "1");
    } catch {
      setDismissed(false);
    }
    api.aiStatus().then(setStatus).catch(() => undefined);
  }, []);

  if (!status || dismissed) return null;
  const rows = [
    { done: true, title: "Clips, captions and downloads", text: "Ready — no key needed." },
    {
      done: status.anthropic.configured,
      title: "Help chat and AI edit planning",
      text: "Needs an Anthropic (Claude) key.",
    },
    { done: status.xai.configured, title: "AI B-roll images and video", text: "Needs a Grok (xAI) key." },
    { done: status.elevenlabs.configured, title: "AI voiceover, music and sound effects", text: "Needs an ElevenLabs key." },
  ];
  if (rows.every((r) => r.done)) return null;

  return (
    <section className="rounded-xl border border-border bg-surface/60 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold">Finish setting up</h2>
          <p className="mt-0.5 text-[13px] text-muted">
            You can make clips right now. Add keys only for the extras you want.
          </p>
        </div>
        <button
          title="Hide"
          aria-label="Hide setup guide"
          className="cursor-pointer rounded-md p-1 text-muted transition hover:bg-surface-2 hover:text-foreground"
          onClick={() => {
            setDismissed(true);
            try {
              localStorage.setItem(DISMISS_KEY, "1");
            } catch {
              /* hidden for this visit only */
            }
          }}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <ul className="mt-4 grid gap-2.5 sm:grid-cols-2">
        {rows.map((r) => (
          <li key={r.title} className="flex items-start gap-2.5 rounded-lg border border-border bg-surface-2/60 px-3 py-2.5">
            {r.done ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            ) : (
              <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
            )}
            <div className="min-w-0">
              <p className={cn("text-[13px] font-semibold", r.done && "text-muted")}>{r.title}</p>
              <p className="text-xs text-muted">
                {r.done ? "Ready." : r.text}{" "}
                {!r.done && (
                  <Link href="/settings" className="font-semibold text-primary hover:underline">
                    Add key
                  </Link>
                )}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
