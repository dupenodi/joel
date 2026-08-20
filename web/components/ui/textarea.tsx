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
        "min-h-[5.5rem] w-full resize-y rounded-control bg-field px-2.5 py-2 text-[14px] leading-relaxed text-ink shadow-hairline outline-none placeholder:text-ink-3 transition-colors duration-150 hover:bg-hover focus:bg-surface focus:shadow-btn disabled:cursor-not-allowed disabled:opacity-50 data-[invalid=true]:shadow-[0_0_0_1px_var(--red)]",
        className,
      )}
      {...props}
    />
  );
});
