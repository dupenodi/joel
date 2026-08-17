import { cn } from "@/lib/utils";

export function Spinner({
  className,
  size = 18,
  tone = "neutral",
}: {
  className?: string;
  size?: number;
  /** "current" adopts the surrounding text color — use inside colored buttons. */
  tone?: "neutral" | "current";
}) {
  return (
    <span
      className={cn(
        "inline-block shrink-0 animate-spin rounded-full border-2",
        tone === "current"
          ? "border-current/30 border-t-current"
          : "border-[var(--line-strong)] border-t-ink",
        className,
      )}
      style={{ width: size, height: size }}
      aria-label="Loading"
      role="status"
    />
  );
}
