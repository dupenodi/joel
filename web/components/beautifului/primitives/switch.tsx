import { cn } from "@/lib/utils";

/** Track fill + knob side follow `checked`. On = ink, knob right. */
export function Switch({
  checked,
  onCheckedChange,
  label,
  className,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onCheckedChange(!checked)}
      className={cn("inline-flex items-center gap-2.5", className)}
    >
      {label && (
        <span className="text-[13px] font-medium text-ink">{label}</span>
      )}
      <span
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors duration-150",
          checked ? "bg-ink" : "bg-line-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 size-4 rounded-full bg-surface shadow-sm transition-transform duration-150",
            checked ? "translate-x-4" : "translate-x-0",
          )}
        />
      </span>
    </button>
  );
}
