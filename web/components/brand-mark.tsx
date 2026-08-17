import { cn } from "@/lib/utils";

/** Ink mark only — matches landing `<joel-logo variant="ink">`. Never red. */
export function BrandMark({
  size = 36,
  className,
  withWordmark = false,
}: {
  size?: number;
  className?: string;
  withWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/brand-kit/logo-ink.svg"
        alt=""
        width={size}
        height={size}
        className="shrink-0"
        style={{
          marginRight: withWordmark ? -Math.round(size * 0.12) : 0,
          filter: "drop-shadow(0 3px 6px rgba(19, 19, 19, 0.14))",
        }}
      />
      {withWordmark && (
        <span
          className="font-display font-semibold tracking-tight text-ink"
          style={{ fontSize: size * 0.52 }}
        >
          Joel
        </span>
      )}
    </span>
  );
}
