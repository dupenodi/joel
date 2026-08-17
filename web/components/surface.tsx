import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Elevation = "flat" | "raised" | "hard";

const elevations: Record<Elevation, string> = {
  flat: "border border-[var(--line)] bg-surface",
  raised: "border border-[var(--line)] bg-surface shadow-[var(--shadow-sm)]",
  hard: "border border-[var(--line)] bg-surface shadow-[var(--shadow-hard)]",
};

export function Surface({
  className,
  elevation = "flat",
  padded = true,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  elevation?: Elevation;
  padded?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius)]",
        elevations[elevation],
        padded && "p-5",
        className,
      )}
      {...props}
    />
  );
}
