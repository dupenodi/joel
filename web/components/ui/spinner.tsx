import { cn } from "@/lib/utils";

export function Spinner({
  className,
  size = 18,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <span
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-[var(--line-strong)] border-t-ink",
        className,
      )}
      style={{ width: size, height: size }}
      aria-label="Loading"
      role="status"
    />
  );
}
