import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Shimmer({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "bg-clip-text font-medium text-transparent",
        className,
      )}
      style={{
        backgroundImage:
          "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
        backgroundSize: "200% 100%",
        animation: "shimmer-text 1.4s linear infinite",
      }}
      {...props}
    >
      {children}
    </span>
  );
}
