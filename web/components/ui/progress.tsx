import { cn } from "@/lib/utils";

export function Progress({
  value,
  segments,
  className,
}: {
  value: number;
  /** Render as N discrete segments (e.g. a multi-step wizard) instead of one continuous bar. */
  segments?: number;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));

  if (segments && segments > 0) {
    const filled = Math.round((clamped / 100) * segments);
    return (
      <div
        className={cn("flex gap-1.5", className)}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {Array.from({ length: segments }, (_, i) => (
          <div
            key={i}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors",
              i < filled ? "bg-ink" : "bg-inset",
            )}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-inset",
        className,
      )}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-ink transition-[width] duration-500"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
