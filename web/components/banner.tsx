import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

const tones = {
  muted: "bg-inset text-ink-soft",
  warn: "bg-[var(--warn-soft)] text-[var(--warn)]",
  accent: "bg-[var(--accent-soft)] text-accent",
  ok: "bg-[var(--ok-soft)] text-[var(--ok)]",
} as const;

export function Banner({
  tone = "muted",
  children,
  className,
}: {
  tone?: keyof typeof tones;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("px-4 py-2.5 text-sm", tones[tone], className)}>
      {children}
    </div>
  );
}
