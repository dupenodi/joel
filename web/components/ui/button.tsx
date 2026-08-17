import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Spinner } from "@/components/ui/spinner";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 font-semibold transition-[transform,box-shadow,background,color,border-color] duration-160 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary:
          "border border-ink bg-ink text-surface shadow-[var(--shadow-sm)] hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]",
        ghost:
          "border border-[var(--line-strong)] bg-transparent text-ink hover:border-ink hover:bg-ink hover:text-surface",
        soft: "border border-transparent bg-inset text-ink hover:bg-[var(--line)]",
        danger:
          "border border-accent bg-accent text-white shadow-[var(--shadow-sm)] hover:-translate-y-0.5",
      },
      size: {
        md: "min-h-[44px] rounded-[var(--radius-pill)] px-5 text-sm",
        sm: "min-h-[36px] rounded-[var(--radius-pill)] px-4 text-sm",
        lg: "min-h-[52px] rounded-[var(--radius-pill)] px-7 text-[0.95rem]",
        icon: "h-9 w-9 rounded-full p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    loading?: boolean;
  };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { className, variant, size, loading, disabled, children, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && <Spinner size={14} tone="current" />}
        {children}
      </button>
    );
  },
);

export { buttonVariants };
