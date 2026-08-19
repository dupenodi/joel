import { cn } from "@/lib/utils";
import { forwardRef, type SelectHTMLAttributes } from "react";

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(function Select(
  { className, children, "aria-invalid": ariaInvalid, ...props },
  ref,
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        aria-invalid={ariaInvalid}
        data-invalid={
          ariaInvalid === true || ariaInvalid === "true" ? "true" : undefined
        }
        className={cn(
          "h-9 w-full appearance-none rounded-control bg-field px-2.5 pr-8 text-[14px] text-ink shadow-hairline outline-none transition-colors duration-150 hover:bg-hover focus:bg-surface focus:shadow-btn disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-ink-3"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </div>
  );
});
