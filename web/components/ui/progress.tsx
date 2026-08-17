import { cn } from "@/lib/utils";

export function Progress({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
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
