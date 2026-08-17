"use client";

import { StatusPill } from "@/components/status-pill";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { ConnectorCard as ConnectorCardData } from "@/lib/types";
import { formatRelative } from "@/lib/utils";
import { PROVIDER_META } from "@/lib/connectors";

export function ConnectorCard({
  card,
  blurb,
  busy,
  onConnect,
  onSync,
  onPause,
  onDisconnect,
  onReconnect,
}: {
  card: ConnectorCardData;
  blurb?: string;
  busy?: boolean;
  onConnect?: () => void;
  onSync?: () => void;
  onPause?: () => void;
  onDisconnect?: () => void;
  onReconnect?: () => void;
}) {
  const meta = PROVIDER_META[card.provider];
  const connected = Boolean(card.id);

  if (card.coming_soon) {
    return (
      <div className="flex items-center gap-3 rounded-[var(--radius)] border border-dashed border-[var(--line)] px-4 py-3 opacity-60">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={meta?.icon} alt="" width={22} height={22} />
        <span className="text-sm font-medium">{card.label}</span>
        <span className="ml-auto">
          <StatusPill status="coming_soon" />
        </span>
      </div>
    );
  }

  return (
    <Surface elevation="raised" className="p-5">
      <div className="flex flex-wrap items-start gap-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={meta?.icon} alt="" width={32} height={32} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-medium">{card.label}</h3>
            <StatusPill status={card.status} />
            {card.mode && (
              <Badge tone="neutral" className="uppercase">
                {card.mode}
              </Badge>
            )}
          </div>
          {(blurb || meta?.blurb) && (
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">
              {blurb ?? meta?.blurb}
            </p>
          )}

          {connected && (
            <>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <Meta label="Docs" value={String(card.doc_count)} />
                <Meta
                  label="Last sync"
                  value={formatRelative(card.last_sync_at)}
                />
                <Meta
                  label="Next sync"
                  value={formatRelative(card.next_sync_at)}
                />
                <Meta
                  label="History"
                  value={
                    card.backfill_done
                      ? "Full history"
                      : card.backfill_progress != null
                        ? `${Math.round(card.backfill_progress * 100)}%`
                        : "—"
                  }
                />
              </dl>
              {card.backfill_progress != null && !card.backfill_done && (
                <Progress
                  className="mt-3"
                  value={card.backfill_progress * 100}
                />
              )}
            </>
          )}

          {card.error && (
            <p className="mt-3 rounded-[var(--radius-sm)] bg-[var(--accent-soft)] px-3 py-2 text-sm text-accent">
              {card.error}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {!connected && (
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={onConnect}
            >
              Connect
            </Button>
          )}
          {connected && card.status === "needs_reauth" && (
            <Button
              type="button"
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={onReconnect}
            >
              Reconnect
            </Button>
          )}
          {connected && card.status !== "needs_reauth" && (
            <>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={onSync}
              >
                Sync now
              </Button>
              <Button
                type="button"
                size="sm"
                variant="soft"
                disabled={busy}
                onClick={onPause}
              >
                Pause
              </Button>
              <Button
                type="button"
                size="sm"
                variant="soft"
                disabled={busy}
                onClick={onDisconnect}
              >
                Disconnect
              </Button>
            </>
          )}
        </div>
      </div>
    </Surface>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
