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
        "h-9 w-full rounded-control bg-field px-2.5 text-[14px] text-ink shadow-hairline outline-none placeholder:text-ink-3 transition-colors duration-150 hover:bg-hover focus:bg-surface focus:shadow-btn disabled:cursor-not-allowed disabled:opacity-50 data-[invalid=true]:shadow-[0_0_0_1px_var(--red)]",
        className,
      )}
      {...props}
    />
  );
});
