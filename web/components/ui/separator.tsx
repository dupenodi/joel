import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Separator({
  className,
  orientation = "horizontal",
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  orientation?: "horizontal" | "vertical";
}) {
  return (
    <div
      role="separator"
      className={cn(
        "shrink-0 bg-[var(--line)]",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      {...props}
    />
  );
}
