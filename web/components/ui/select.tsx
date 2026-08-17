import { cn } from "@/lib/utils";
import type { SelectHTMLAttributes } from "react";

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full appearance-none rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--inset)] bg-[length:12px] bg-[right_12px_center] bg-no-repeat px-3.5 py-2.5 pr-9 text-[15px] text-ink outline-none focus:border-[var(--line-strong)] focus:bg-surface focus:shadow-[var(--shadow-sm)]",
        className,
      )}
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%238b8b8e' d='M3 4.5 6 8l3-3.5'/%3E%3C/svg%3E")`,
      }}
      {...props}
    >
      {children}
    </select>
  );
}
