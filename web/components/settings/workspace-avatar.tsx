import { cn } from "@/lib/utils";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
}

export function WorkspaceAvatar({
  name,
  logoUrl,
  size = 36,
  className,
}: {
  name: string;
  logoUrl?: string | null;
  size?: number;
  className?: string;
}) {
  const dim = `${size}px`;
  if (logoUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logoUrl}
        alt=""
        width={size}
        height={size}
        className={cn("shrink-0 rounded-control bg-inset object-cover", className)}
        style={{ width: dim, height: dim }}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-control bg-ink text-page font-medium",
        className,
      )}
      style={{ width: dim, height: dim, fontSize: Math.max(10, size * 0.32) }}
    >
      {initials(name)}
    </span>
  );
}

export function PersonAvatar({
  name,
  size = 28,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const dim = `${size}px`;
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-field text-ink-2 font-medium",
        className,
      )}
      style={{ width: dim, height: dim, fontSize: Math.max(10, size * 0.36) }}
    >
      {initials(name)}
    </span>
  );
}
