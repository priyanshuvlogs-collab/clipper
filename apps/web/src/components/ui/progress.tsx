import { cn } from "@/lib/utils";

export function Progress({
  value,
  className,
  indeterminate = false,
}: {
  value: number;
  className?: string;
  indeterminate?: boolean;
}) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-surface-2", className)}>
      <div
        className={cn(
          "h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-500",
          indeterminate && "animate-pulse",
        )}
        style={{ width: `${Math.min(100, Math.max(indeterminate ? 100 : 0, value))}%` }}
      />
    </div>
  );
}
