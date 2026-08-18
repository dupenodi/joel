"use client";

import { Field } from "@/components/field";
import { JobHistoryRow } from "@/components/job-row";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { listSlackChannels } from "@/lib/api";
import type { IntegrationDef } from "@/lib/integrations";
import {
  INTERVAL_OPTIONS,
  LOOKBACK_OPTIONS,
  integrationLogoUrl,
} from "@/lib/integrations";
import type { ConnectorCard, JobRow } from "@/lib/types";
import { formatRelative } from "@/lib/utils";
import { X } from "lucide-react";
import { useEffect, useState } from "react";

export function IntegrationModal({
  open,
  onClose,
  def,
  card,
  jobs,
  connected,
  identity,
  configured,
  busy,
  error,
  onConnect,
  onStartIngest,
  onSync,
  onDisconnect,
  onPatch,
}: {
  open: boolean;
  onClose: () => void;
  def: IntegrationDef;
  card: ConnectorCard | null;
  jobs: JobRow[];
  connected: boolean;
  identity: string | null;
  configured: boolean;
  busy: string | null;
  error: string | null;
  onConnect: () => void;
  onStartIngest: (input: {
    lookbackDays: number;
    channelIds: string[];
  }) => void;
  onSync: () => void;
  onDisconnect: () => void;
  onPatch: (body: { interval_min?: number; lookback_days?: number }) => void;
}) {
  const [lookback, setLookback] = useState(
    card?.lookback_days ?? def.defaultLookbackDays,
  );
  const [channels, setChannels] = useState<
    Array<{ id: string; name: string; is_private: boolean }>
  >([]);
  const [selected, setSelected] = useState<string[]>(card?.channel_ids ?? []);
  const [channelError, setChannelError] = useState<string | null>(null);
  const isSlack = def.id === "slack";
  const needsSetup =
    Boolean(def.ingest) &&
    connected &&
    (isSlack
      ? !(card?.channel_ids && card.channel_ids.length > 0)
      : !card?.last_sync_at);

  useEffect(() => {
    if (!open || !isSlack || !card?.id) return;
    setChannelError(null);
    listSlackChannels(card.id)
      .then((list) => {
        setChannels(list);
        setSelected((current) =>
          current.length > 0 ? current : (card?.channel_ids ?? []),
        );
      })
      .catch((e) =>
        setChannelError(e instanceof Error ? e.message : "Could not list channels"),
      );
  }, [open, isSlack, card?.id]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  }

  return (
    <Dialog open={open} onClose={onClose} title={def.name}>
      <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={integrationLogoUrl(def.toolkit)} alt="" width={36} height={36} />
          <div>
            <h2 className="font-display text-xl font-semibold tracking-tight">
              {def.name}
            </h2>
            {identity && (
              <p className="text-sm text-ink-soft">{identity}</p>
            )}
          </div>
        </div>
        <IconButton aria-label="Close" onClick={onClose}>
          <X size={18} />
        </IconButton>
      </div>

      <div className="max-h-[min(72vh,640px)] space-y-5 overflow-y-auto px-5 py-5">
        <p className="text-sm leading-relaxed text-ink-soft">{def.scope}</p>

        {error && <p className="text-sm text-accent">{error}</p>}
        {channelError && <p className="text-sm text-accent">{channelError}</p>}

        {!def.connectable && (
          <p className="text-sm text-muted">
            Not available yet. It’ll show up here when ingest is ready.
          </p>
        )}

        {def.connectable && !connected && (
          <>
            <p className="text-sm text-muted">
              {isSlack
                ? "Connect first. You’ll pick channels and how far back after Slack comes back."
                : def.id === "gmail" || def.id === "googledrive"
                  ? "Google only allows Composio’s verified Gmail/Drive scopes. Joel requests readonly access only. If you see “This app is blocked”, connect again. Own Google OAuth client: composio.dev/auth/googleapps"
                  : `Connect first. You’ll pick how far back after ${def.name} comes back.`}
            </p>
            <Button
              type="button"
              disabled={!configured || busy != null}
              loading={busy === "connect"}
              onClick={onConnect}
            >
              Connect
            </Button>
            {!configured && (
              <p className="text-sm text-muted">
                Save a Composio API key first.
              </p>
            )}
          </>
        )}

        {connected && card && def.ingest && (
          <>
            {isSlack && (
              <>
                <Field label="Channels">
                  <div className="max-h-56 space-y-2 overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--line)] bg-inset p-3">
                    {channels.length === 0 && !channelError ? (
                      <p className="text-sm text-muted">Loading channels…</p>
                    ) : (
                      channels.map((channel) => (
                        <label
                          key={channel.id}
                          className="flex items-center gap-2 text-sm"
                        >
                          <Checkbox
                            checked={selected.includes(channel.id)}
                            onChange={() => toggle(channel.id)}
                          />
                          <span>
                            #{channel.name}
                            {channel.is_private ? (
                              <span className="ml-1 text-muted">private</span>
                            ) : null}
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                </Field>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelected(channels.map((c) => c.id))}
                  >
                    All
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelected([])}
                  >
                    None
                  </Button>
                </div>
              </>
            )}
            {(needsSetup || isSlack) && (
              <Field label="How far back">
                <Select
                  value={String(lookback)}
                  onChange={(e) => setLookback(Number(e.target.value))}
                >
                  {LOOKBACK_OPTIONS.map((option) => (
                    <option key={option.days} value={option.days}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {needsSetup && (
              <Button
                type="button"
                disabled={
                  (isSlack && selected.length === 0) || busy != null
                }
                loading={busy === "ingest" || busy === "sync"}
                onClick={() =>
                  onStartIngest({
                    lookbackDays: lookback,
                    channelIds: isSlack ? selected : [],
                  })
                }
              >
                Start ingest
              </Button>
            )}
          </>
        )}

        {connected && card && !needsSetup && (
          <>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-muted">Docs</dt>
                <dd className="font-medium tabular-nums">{card.doc_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Last sync</dt>
                <dd className="font-medium">{formatRelative(card.last_sync_at)}</dd>
              </div>
            </dl>
            {card.error && (
              <p className="rounded-[var(--radius-sm)] bg-[var(--accent-soft)] px-3 py-2 text-sm text-accent">
                {card.error}
              </p>
            )}
            {def.ingest ? (
              <>
                <Field label="Sync interval">
                  <Select
                    value={String(card.interval_min)}
                    onChange={(e) =>
                      onPatch({ interval_min: Number(e.target.value) })
                    }
                  >
                    {INTERVAL_OPTIONS.map((option) => (
                      <option key={option.minutes} value={option.minutes}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                {isSlack && (
                  <Button
                    type="button"
                    size="sm"
                    disabled={selected.length === 0 || busy != null}
                    loading={busy === "ingest" || busy === "sync"}
                    onClick={() =>
                      onStartIngest({
                        lookbackDays: lookback,
                        channelIds: selected,
                      })
                    }
                  >
                    Save and sync
                  </Button>
                )}
                {!isSlack && (
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy != null}
                    loading={busy === "sync"}
                    onClick={onSync}
                  >
                    Sync now
                  </Button>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">
                Connected through Composio. Ingest for this tool isn’t shipped
                yet, so Sync now stays off.
              </p>
            )}
          </>
        )}

        {connected && card && (
          <>
            {def.ingest && jobs.length > 0 && (
              <div>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.06em] text-muted">
                  Job history
                </h3>
                {jobs.map((job) => (
                  <JobHistoryRow key={job.id} job={job} />
                ))}
              </div>
            )}
            <Button
              type="button"
              size="sm"
              variant="soft"
              disabled={busy != null}
              loading={busy === "disconnect"}
              onClick={onDisconnect}
            >
              Disconnect
            </Button>
          </>
        )}
      </div>
    </Dialog>
  );
}
