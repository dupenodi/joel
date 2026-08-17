import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function Avatar({
  name,
  src,
  size = 40,
  className,
  ...props
}: {
  name: string;
  src?: string | null;
  size?: number;
} & HTMLAttributes<HTMLDivElement>) {
  const initial = name.trim().charAt(0).toUpperCase() || "?";

  return (
    <div
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-ink font-semibold text-surface",
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden={props["aria-label"] ? undefined : true}
      {...props}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" width={size} height={size} className="h-full w-full object-cover" />
      ) : (
        initial
      )}
    </div>
  );
}
