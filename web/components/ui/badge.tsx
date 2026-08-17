import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide",
  {
    variants: {
      tone: {
        neutral: "bg-inset text-ink-soft",
        ink: "bg-ink text-surface",
        ok: "bg-[var(--ok-soft)] text-[var(--ok)]",
        warn: "bg-[var(--warn-soft)] text-[var(--warn)]",
        partial: "bg-[var(--partial-soft)] text-[var(--partial)]",
        accent: "bg-[var(--accent-soft)] text-accent",
        muted: "bg-[var(--absent-soft)] text-[var(--absent)]",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeProps = HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>;

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export { badgeVariants };
