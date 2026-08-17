import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto flex max-w-md flex-col items-center px-6 py-16 text-center",
        className,
      )}
    >
      <BrandMark size={48} />
      <h2 className="mt-5 font-display text-2xl font-semibold tracking-tight">
        {title}
      </h2>
      {description && (
        <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

/** Convenience CTA for mock empty states */
export function EmptyStateButton({
  children,
  ...props
}: React.ComponentProps<typeof Button>) {
  return (
    <Button type="button" {...props}>
      {children}
    </Button>
  );
}
