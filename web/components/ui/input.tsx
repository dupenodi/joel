import { cn } from "@/lib/utils";
import type { InputHTMLAttributes } from "react";

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--inset)] px-3.5 py-2.5 text-[15px] text-ink outline-none transition-[border-color,background,box-shadow] placeholder:text-muted focus:border-[var(--line-strong)] focus:bg-surface focus:shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    />
  );
}
