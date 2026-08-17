import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "mb-8 flex flex-wrap items-end justify-between gap-4",
        className,
      )}
    >
      <div className="max-w-xl">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
