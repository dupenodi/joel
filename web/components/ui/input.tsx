import { cn } from "@/lib/utils";
import { forwardRef, type InputHTMLAttributes } from "react";

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, "aria-invalid": ariaInvalid, ...props }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={ariaInvalid}
      data-invalid={ariaInvalid === true || ariaInvalid === "true" ? "true" : undefined}
      className={cn(
        "w-full rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--inset)] px-3.5 py-2.5 text-[15px] text-ink outline-none transition-[border-color,background,box-shadow] placeholder:text-muted focus:border-[var(--line-strong)] focus:bg-surface focus:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50 data-[invalid=true]:border-accent data-[invalid=true]:bg-[var(--accent-soft)] data-[invalid=true]:focus:border-accent",
        className,
      )}
      {...props}
    />
  );
});
