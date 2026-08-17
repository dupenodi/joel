import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";
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
          "w-full appearance-none rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--inset)] px-3.5 py-2.5 pr-9 text-[15px] text-ink outline-none transition-[border-color,background,box-shadow] focus:border-[var(--line-strong)] focus:bg-surface focus:shadow-[var(--shadow-sm)] disabled:cursor-not-allowed disabled:opacity-50 data-[invalid=true]:border-accent data-[invalid=true]:bg-[var(--accent-soft)] data-[invalid=true]:focus:border-accent",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        size={14}
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-muted"
      />
    </div>
  );
});
