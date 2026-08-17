import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement>
>(function IconButton({ className, type = "button", ...props }, ref) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-inset hover:text-ink disabled:pointer-events-none disabled:opacity-45",
        className,
      )}
      {...props}
    />
  );
});
