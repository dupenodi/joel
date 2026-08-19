import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

/** Light-mode Beautiful UI token scope. Wrap any primitive before use. */
export function BuiScope({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bui", className)} {...props} />;
}
