import { cn } from "@/lib/utils";
import { forwardRef, type TextareaHTMLAttributes } from "react";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, "aria-invalid": ariaInvalid, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      aria-invalid={ariaInvalid}
      data-invalid={ariaInvalid === true || ariaInvalid === "true" ? "true" : undefined}
      className={cn(
        "min-h-[96px] w-full resize-y rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--inset)] px-3.5 py-2.5 text-[15px] text-ink outline-none transition-[border-color,background,box-shadow] placeholder:text-muted focus:border-[var(--line-strong)] focus:bg-surface focus:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50 data-[invalid=true]:border-accent data-[invalid=true]:bg-[var(--accent-soft)] data-[invalid=true]:focus:border-accent",
        className,
      )}
      {...props}
    />
  );
});
