import { Badge } from "@/components/ui/badge";
import type { AnswerStatus, ConnectorStatus } from "@/lib/types";

const connectorMap: Record<
  ConnectorStatus,
  { label: string; tone: "neutral" | "ok" | "partial" | "accent" | "muted" }
> = {
  pending_auth: { label: "Not connected", tone: "muted" },
  pending_setup: { label: "Pick channels", tone: "partial" },
  backfilling: { label: "Backfilling", tone: "partial" },
  distilling: { label: "Distilling", tone: "partial" },
  linking: { label: "Linking", tone: "partial" },
  ready: { label: "Ready", tone: "ok" },
  syncing: { label: "Syncing", tone: "partial" },
  needs_reauth: { label: "Needs reconnect", tone: "accent" },
  error: { label: "Error", tone: "accent" },
  coming_soon: { label: "Coming soon", tone: "muted" },
};

const answerMap: Record<
  AnswerStatus,
  { glyph: string; label: string; tone: "ok" | "partial" | "warn" | "muted" }
> = {
  answered: { glyph: "✅", label: "Answered", tone: "ok" },
  partial: { glyph: "🟡", label: "Partial", tone: "partial" },
  conflicted: { glyph: "⚠️", label: "Conflicted", tone: "warn" },
  absent: { glyph: "🚫", label: "Not in memory", tone: "muted" },
};

export function StatusPill({ status }: { status: ConnectorStatus }) {
  const s = connectorMap[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function AnswerBadge({ status }: { status: AnswerStatus }) {
  const s = answerMap[status];
  return (
    <Badge tone={s.tone}>
      <span aria-hidden>{s.glyph}</span>
      {s.label}
    </Badge>
  );
}
