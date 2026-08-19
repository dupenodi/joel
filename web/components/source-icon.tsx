import { PROVIDER_META } from "@/lib/connectors";
import { cn } from "@/lib/utils";

export function SourceIcon({
  provider,
  size = 16,
  className,
}: {
  provider?: string | null;
  size?: number;
  className?: string;
}) {
  const meta = provider ? PROVIDER_META[provider] : null;
  if (!meta?.icon) {
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full bg-inset text-[10px] font-medium text-ink-3",
          className,
        )}
        style={{ width: size, height: size }}
      >
        ·
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={meta.icon}
      alt=""
      width={size}
      height={size}
      className={cn("inline-block shrink-0", className)}
    />
  );
}
