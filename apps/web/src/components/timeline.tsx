"use client";

import { type ClipData } from "@/lib/api";
import { cn, formatTime } from "@/lib/utils";

/** Horizontal strip showing where each detected clip sits in the source video. */
export function Timeline({
  duration,
  clips,
  selectedId,
  onSelect,
}: {
  duration: number;
  clips: ClipData[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (duration <= 0 || clips.length === 0) return null;

  return (
    <div>
      <div className="relative h-12 w-full overflow-hidden rounded-lg border border-border bg-surface-2">
        {/* minute grid */}
        {Array.from({ length: Math.floor(duration / 60) }, (_, i) => (
          <div
            key={i}
            className="absolute top-0 h-full w-px bg-border/60"
            style={{ left: `${((i + 1) * 60 * 100) / duration}%` }}
          />
        ))}
        {clips.map((clip, i) => {
          const left = (clip.start / duration) * 100;
          const width = Math.max(0.8, ((clip.end - clip.start) / duration) * 100);
          return (
            <button
              key={clip.id}
              title={`${clip.title} (${formatTime(clip.start)} – ${formatTime(clip.end)})`}
              onClick={() => onSelect(clip.id)}
              className={cn(
                "absolute top-1.5 flex h-9 cursor-pointer items-center justify-center overflow-hidden rounded-md border text-[10px] font-bold transition",
                selectedId === clip.id
                  ? "z-10 border-accent bg-accent/40 text-white ring-2 ring-accent/50"
                  : "border-primary/60 bg-primary/30 text-primary hover:bg-primary/50 hover:text-white",
              )}
              style={{ left: `${left}%`, width: `${width}%` }}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted">
        <span>0:00</span>
        <span>{formatTime(duration)}</span>
      </div>
    </div>
  );
}
