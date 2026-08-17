import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Chip({
  className,
  active,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { active?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "border-ink bg-ink text-surface"
          : "border-[var(--line)] bg-surface text-ink-soft",
        className,
      )}
      {...props}
    />
  );
}

export function Kbd({
  className,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-[1.4em] items-center justify-center rounded-md border border-[var(--line-strong)] bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink-soft shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    />
  );
}
