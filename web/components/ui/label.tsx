import { cn } from "@/lib/utils";
import type { LabelHTMLAttributes } from "react";

export function Label({
  className,
  ...props
}: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "block text-xs font-medium uppercase tracking-[0.06em] text-muted",
        className,
      )}
      {...props}
    />
  );
}
