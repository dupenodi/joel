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
      className={cn("mb-6 flex flex-wrap items-end justify-between gap-3", className)}
    >
      <div className="max-w-xl">
        <h1 className="text-[17px] font-semibold tracking-tight text-ink">{title}</h1>
        {description && (
          <p className="mt-1 text-[14px] leading-relaxed text-ink-2">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
