import { cn } from "@/lib/utils";

export function StepIndicator({
  step,
  total,
  label,
}: {
  step: number;
  total: number;
  label?: string;
}) {
  return (
    <div>
      {label && <p className="text-sm text-muted">{label}</p>}
      <div className="mt-3 flex gap-1.5">
        {Array.from({ length: total }, (_, i) => (
          <div
            key={i}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors",
              i < step ? "bg-ink" : "bg-[var(--line)]",
            )}
          />
        ))}
      </div>
    </div>
  );
}
