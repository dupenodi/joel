import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type MemoryBannerKind =
  | "ingesting"
  | "reauth"
  | "degraded"
  | "llm"
  | "disk"
  | "rebuild";

const TONE: Record<
  MemoryBannerKind,
  { className: string; label: string }
> = {
  ingesting: {
    className: "bg-inset text-ink-2",
    label: "Still ingesting — answers may be incomplete.",
  },
  reauth: {
    className: "bg-accent-tint text-accent-ink",
    label: "A connector needs reconnect.",
  },
  degraded: {
    className: "bg-orange-tint text-orange",
    label: "Relationship search unavailable — answering on five lanes.",
  },
  llm: {
    className: "bg-red-tint text-red",
    label: "LLM key rejected. Ingestion is paused.",
  },
  disk: {
    className: "bg-red-tint text-red",
    label: "Disk full. Sync stopped — no partial writes.",
  },
  rebuild: {
    className: "bg-inset text-ink-2",
    label: "Graph model changed. Rebuilding from canonical in the background.",
  },
};

export function MemoryBanner({
  kind,
  children,
  action,
  className,
}: {
  kind: MemoryBannerKind;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const t = TONE[kind];
  return (
    <div
      className={cn(
        `flex items-center gap-3 px-3 py-2 text-[12.5px] leading-snug ${t.className}`,
        className,
      )}
    >
      <p className="min-w-0 flex-1">{children ?? t.label}</p>
      {action}
    </div>
  );
}
