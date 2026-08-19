import { cn } from "@/lib/utils";
import type { LabelHTMLAttributes } from "react";

export function Label({
  className,
  ...props
}: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("block text-[11.5px] font-medium text-ink-2", className)}
      {...props}
    />
  );
}
