"use client";

import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onChange,
  label,
  className,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn("flex cursor-pointer items-center gap-2.5 text-sm", className)}
    >
      <span
        className={cn(
          "relative inline-flex h-5.5 w-10 shrink-0 items-center rounded-full border transition-colors",
          checked ? "border-primary bg-primary" : "border-border bg-surface-2",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-5" : "translate-x-1",
          )}
        />
      </span>
      {label && <span className="text-[13px] text-foreground">{label}</span>}
    </button>
  );
}
