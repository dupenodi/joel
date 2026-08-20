import { cn } from "@/lib/utils";

export function SettingsSection({
  title,
  description,
  children,
  className,
  headerAside,
  danger,
}: {
  title?: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerAside?: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <section
      className={cn(
        "rounded-card p-5 shadow-card",
        danger ? "bg-red-tint" : "bg-surface",
        className,
      )}
    >
      {(title || description || headerAside) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 max-w-xl">
            {title && (
              <h2
                className={cn(
                  "text-[15px] font-semibold tracking-tight",
                  danger ? "text-red" : "text-ink",
                )}
              >
                {title}
              </h2>
            )}
            {description && (
              <div className="mt-1 text-[13px] leading-relaxed text-ink-2">
                {description}
              </div>
            )}
          </div>
          {headerAside}
        </div>
      )}
      {children}
    </section>
  );
}

export function SettingsEmpty({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-dashed border-line bg-field/60 px-4 py-8 text-center text-[13px] text-ink-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
