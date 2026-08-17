"use client";

import { cn } from "@/lib/utils";

export function Switch({
  checked = false,
  onCheckedChange,
  disabled,
  label,
  className,
}: {
  checked?: boolean;
  onCheckedChange?: (next: boolean) => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full border transition-colors",
        checked ? "border-ink bg-ink" : "border-[var(--line-strong)] bg-inset",
        disabled && "opacity-45",
        className,
      )}
    >
      <span
        className={cn(
          "absolute top-[3px] left-[3px] h-[18px] w-[18px] rounded-full bg-surface shadow-[var(--shadow-sm)] transition-transform",
          checked && "translate-x-[20px]",
        )}
      />
    </button>
  );
}
