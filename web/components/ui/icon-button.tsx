import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

export function IconButton({
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-inset hover:text-ink disabled:opacity-45",
        className,
      )}
      {...props}
    />
  );
}
