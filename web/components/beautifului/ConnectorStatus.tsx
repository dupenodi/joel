import type { ConnectorStatus as Status } from "@/lib/types";
import { surfaceStatus } from "@/lib/connectors";

const COPY: Record<Status, { label: string; className: string }> = {
  pending_auth: { label: "Not connected", className: "bg-field text-ink-3" },
  pending_setup: { label: "Needs setup", className: "bg-orange-tint text-orange" },
  backfilling: { label: "Syncing", className: "bg-accent-tint text-accent-ink" },
  distilling: { label: "Syncing", className: "bg-accent-tint text-accent-ink" },
  linking: { label: "Syncing", className: "bg-accent-tint text-accent-ink" },
  ready: { label: "Connected", className: "bg-green-tint text-green" },
  syncing: { label: "Syncing", className: "bg-accent-tint text-accent-ink" },
  needs_reauth: { label: "Reconnect", className: "bg-red-tint text-red" },
  error: { label: "Error", className: "bg-red-tint text-red" },
  coming_soon: { label: "Soon", className: "bg-field text-ink-3" },
};

export function ConnectorStatus({ status }: { status: Status }) {
  const s = COPY[surfaceStatus(status)];
  return (
    <span
      className={`inline-flex h-5.5 items-center rounded-full px-2 text-[11.5px] font-medium ${s.className}`}
    >
      {s.label}
    </span>
  );
}
