import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type BoneRadius = "control" | "card" | "full";

const RADIUS: Record<BoneRadius, string> = {
  control: "rounded-control",
  card: "rounded-card",
  full: "rounded-full",
};

/** Hollow stand-in for content that has a known shape. Pulse, not shimmer. */
export function Bone({
  className,
  rounded = "control",
  style,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { rounded?: BoneRadius }) {
  return (
    <span
      aria-hidden
      className={cn(
        "block bg-field",
        RADIUS[rounded],
        className,
      )}
      style={{ animation: "bone-pulse 1.6s ease-in-out infinite", ...style }}
      {...props}
    />
  );
}
