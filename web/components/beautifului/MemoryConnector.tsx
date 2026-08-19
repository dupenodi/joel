"use client";

import { ConnectorStatus } from "@/components/beautifului/ConnectorStatus";
import { Button } from "@/components/beautifului/primitives/button";
import { SourceIcon } from "@/components/source-icon";
import type { ConnectorCard } from "@/lib/types";

export function MemoryConnector({
  card,
  blurb,
  busy,
  onConnect,
  onSync,
  onDisconnect,
  onReconnect,
}: {
  card: ConnectorCard;
  blurb?: string;
  busy?: boolean;
  onConnect?: () => void;
  onSync?: () => void;
  onDisconnect?: () => void;
  onReconnect?: () => void;
}) {
  const connected = Boolean(card.id);

  if (card.coming_soon) {
    return (
      <div className="flex items-center gap-2.5 rounded-control px-3 py-2 opacity-60">
        <SourceIcon provider={card.provider} size={18} />
        <span className="text-[13px] font-medium text-ink">{card.label}</span>
        <span className="ml-auto">
          <ConnectorStatus status="coming_soon" />
        </span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-lg overflow-hidden rounded-card bg-surface shadow-card">
      <div className="flex items-start gap-3 p-3">
        <SourceIcon provider={card.provider} size={22} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-ink">{card.label}</h3>
            <ConnectorStatus status={card.status} />
          </div>
          {blurb && (
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{blurb}</p>
          )}
          {connected && (
            <dl className="mt-3 grid grid-cols-3 gap-2">
              <Meta label="Docs" value={card.doc_count.toLocaleString()} />
              <Meta label="Last" value={card.last_sync_at ?? "—"} />
              <Meta label="Next" value={card.next_sync_at ?? "—"} />
            </dl>
          )}
          {card.error && (
            <p className="mt-2 rounded-control bg-red-tint px-2 py-1.5 text-[12px] text-red">
              {card.error}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          {!connected && (
            <Button size="sm" variant="accent" disabled={busy} onClick={onConnect}>
              Connect
            </Button>
          )}
          {connected && card.status === "needs_reauth" && (
            <Button size="sm" variant="danger" disabled={busy} onClick={onReconnect}>
              Reconnect
            </Button>
          )}
          {connected && card.status !== "needs_reauth" && (
            <>
              <Button size="sm" variant="secondary" disabled={busy} onClick={onSync}>
                Sync now
              </Button>
              <Button size="sm" variant="secondary" disabled={busy} onClick={onDisconnect}>
                Disconnect
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd className="text-[12.5px] font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
