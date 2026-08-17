"use client";

import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type SwitchProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onChange" | "type"
> & {
  checked?: boolean;
  onCheckedChange?: (next: boolean) => void;
  label?: string;
};

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(
  function Switch(
    { checked = false, onCheckedChange, label, disabled, className, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onCheckedChange?.(!checked)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-45",
          checked ? "border-ink bg-ink" : "border-[var(--line)] bg-inset",
          className,
        )}
        {...props}
      >
        <span
          className={cn(
            "absolute top-[3px] left-[3px] h-[18px] w-[18px] rounded-full bg-surface shadow-[var(--shadow-sm)] transition-transform",
            checked && "translate-x-[20px]",
          )}
        />
      </button>
    );
  },
);
