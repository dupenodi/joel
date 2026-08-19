import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

const buiButton = cva(
  "inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-full font-medium transition-[background-color,color,box-shadow,transform] duration-150 enabled:active:scale-[0.97] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40",
  {
    variants: {
      variant: {
        primary: "bg-field text-ink shadow-btn hover:bg-hover",
        secondary: "bg-transparent text-ink-2 hover:bg-hover hover:text-ink",
        accent: "bg-ink text-canvas shadow-hairline hover:opacity-90",
        success: "bg-green text-white hover:opacity-90",
        danger: "bg-red-tint text-red hover:bg-red hover:text-white",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        md: "h-9 px-3.5 text-[14px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export type ButtonVariant = NonNullable<
  VariantProps<typeof buiButton>["variant"]
>;

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buiButton> & { loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { className, variant, size, type = "button", loading, disabled, children, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(buiButton({ variant, size }), className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && (
          <span className="size-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent" />
        )}
        {children}
      </button>
    );
  },
);
