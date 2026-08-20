"use client";

import { ConnectorStatus } from "@/components/beautifului/ConnectorStatus";
import LoadingState from "@/components/beautifului/LoadingState";
import { Field } from "@/components/field";
import { LastPull } from "@/components/job-row";
import { ChannelListSkeleton, LastPullSkeleton } from "@/components/skeletons";
import { Button } from "@/components/beautifului/primitives/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { listSlackChannels } from "@/lib/api";
import { isSyncing } from "@/lib/connectors";
import type { IntegrationDef } from "@/lib/integrations";
import {
  INTERVAL_OPTIONS,
  LOOKBACK_OPTIONS,
  integrationLogoUrl,
} from "@/lib/integrations";
import type { ConnectorCard, JobRow } from "@/lib/types";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export function IntegrationModal({
  open,
  onClose,
  def,
  card,
  jobs,
  jobsLoading = false,
  connected,
  identity,
  configured,
  isAdmin,
  busy,
  error,
  onConnect,
  onStartIngest,
  onSync,
  onCancel,
  onDisconnect,
  onPatch,
}: {
  open: boolean;
  onClose: () => void;
  def: IntegrationDef;
  card: ConnectorCard | null;
  jobs: JobRow[];
  jobsLoading?: boolean;
  connected: boolean;
  identity: string | null;
  configured: boolean;
  isAdmin: boolean;
  busy: string | null;
  error: string | null;
  onConnect: (personal: boolean) => void;
  onStartIngest: (input: {
    lookbackDays: number;
    channelIds: string[];
  }) => void;
  onSync: () => void;
  onCancel: () => void;
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
  const [channelsLoading, setChannelsLoading] = useState(false);
  // §0.3/§1.4: only mailbox/DM-shaped providers can be personal -- a
  // second Notion/Drive connection wouldn't mean anything different from
  // the org-shared one, so the choice is only offered here, matching the
  // server-side PERSONAL_CONNECTOR_PROVIDERS allowlist it's checked
  // against regardless.
  const canBePersonal = def.id === "gmail" || def.id === "slack";
  const [personal, setPersonal] = useState(!isAdmin && canBePersonal);
  const connectPersonal = isAdmin ? personal : canBePersonal;
  const canConnect = isAdmin || canBePersonal;
  const canManage = Boolean(card?.id) && (Boolean(card?.personal) || isAdmin);
  const pickedRef = useRef(false);
  const selectModeRef = useRef<"all" | "none" | null>(null);
  const isSlack = def.id === "slack";
  const needsSetup =
    Boolean(def.ingest) &&
    connected &&
    (isSlack
      ? !(card?.channel_ids && card.channel_ids.length > 0)
      : !card?.last_sync_at);
  const needsReauth = card?.status === "needs_reauth";
  const inFlight =
    isSyncing(card?.status) ||
    jobs[0]?.status === "running" ||
    busy === "ingest" ||
    busy === "sync";
  const live = connected && Boolean(card) && !needsSetup && !inFlight;

  useEffect(() => {
    if (!open || !isSlack || !card?.id || !canManage) return;
    setChannelError(null);
    setChannelsLoading(true);
    listSlackChannels(card.id)
      .then((list) => {
        setChannels(list);
        setSelected((current) => {
          if (selectModeRef.current === "all") return list.map((channel) => channel.id);
          if (selectModeRef.current === "none") return [];
          if (pickedRef.current) return current;
          if (current.length > 0) return current;
          return card?.channel_ids ?? [];
        });
      })
      .catch((e) =>
        setChannelError(e instanceof Error ? e.message : "Could not list channels"),
      )
      .finally(() => setChannelsLoading(false));
  }, [open, isSlack, card?.id, canManage]);

  function toggle(id: string) {
    pickedRef.current = true;
    selectModeRef.current = null;
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  }

  function startOrSave() {
    onStartIngest({
      lookbackDays: lookback,
      channelIds: isSlack ? selected : [],
    });
  }

  const slackBlocked = isSlack && selected.length === 0;
  const primary = !def.connectable
    ? null
    : (!connected || needsReauth) && canConnect
      ? {
          label: needsReauth ? `Reconnect ${def.name}` : `Connect ${def.name}`,
          disabled: !configured || busy != null,
          loading: busy === "connect",
          variant: "accent" as const,
          onClick: () => onConnect(connectPersonal),
        }
      : !canManage
        ? null
        : inFlight
        ? {
            label: "Cancel",
            disabled: busy != null && busy !== "ingest" && busy !== "sync",
            loading: busy === "cancel",
            variant: "secondary" as const,
            onClick: onCancel,
          }
      : needsSetup && def.ingest
        ? {
            label: "Start pulling",
            disabled: slackBlocked || busy != null,
            loading: busy === "ingest",
            variant: "accent" as const,
            onClick: startOrSave,
          }
        : connected && def.ingest
          ? {
              label: "Sync now",
              disabled: slackBlocked || busy != null,
              loading: false,
              variant: "accent" as const,
              onClick: isSlack ? startOrSave : onSync,
            }
          : null;

  const permissions = def.permissions.length > 0 && (
    <div className="space-y-1.5">
      <p className="text-[11.5px] font-medium text-ink-2">Permissions</p>
      <ul className="flex flex-wrap gap-1.5">
        {def.permissions.map((perm) => (
          <li
            key={perm}
            className="rounded-[var(--radius-chip)] bg-inset px-2 py-0.5 font-mono text-[11.5px] text-ink-2"
          >
            {perm}
          </li>
        ))}
      </ul>
      {def.permissionNote && (
        <p className="text-[12.5px] leading-relaxed text-ink-3">
          {def.permissionNote}
        </p>
      )}
    </div>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={def.name}
      locked={busy === "connect"}
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={integrationLogoUrl(def.toolkit)} alt="" width={28} height={28} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold tracking-tight text-ink">
                {def.name}
              </h2>
              {card ? (
                <ConnectorStatus
                  status={!def.connectable ? "coming_soon" : card.status}
                />
              ) : (
                <ConnectorStatus
                  status={def.connectable ? "pending_auth" : "coming_soon"}
                />
              )}
            </div>
            {identity && (
              <p className="truncate text-[12.5px] text-ink-2">{identity}</p>
            )}
          </div>
        </div>
        <button
          type="button"
          aria-label="Close"
          disabled={busy === "connect"}
          onClick={onClose}
          className="flex size-7 shrink-0 items-center justify-center rounded-control text-ink-3 hover:bg-hover hover:text-ink disabled:opacity-40"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {error && <p className="text-[12.5px] text-red">{error}</p>}
        {channelError && <p className="text-[12.5px] text-red">{channelError}</p>}

        {!def.connectable && (
          <p className="text-[13px] text-ink-3">Not available yet.</p>
        )}

        {def.connectable && !connected && !configured && (
          <p className="text-[13px] text-ink-3">
            {isAdmin
              ? "Save a Composio API key first."
              : "Ask an admin to add a Composio API key first."}
          </p>
        )}

        {def.connectable && !connected && configured && !canConnect && (
          <p className="text-[13px] text-ink-3">
            Ask an admin to connect this.
          </p>
        )}

        {!connected && permissions}

        {!connected && canBePersonal && isAdmin && (
          <label className="flex cursor-pointer items-start gap-2 text-[13px] text-ink">
            <Checkbox checked={personal} onChange={() => setPersonal((p) => !p)} />
            <span>
              Just for me
              <span className="block text-[12.5px] text-ink-2">
                Only you can ask questions using this connection — it won't be shared with the workspace.
              </span>
            </span>
          </label>
        )}

        {!connected && canBePersonal && !isAdmin && (
          <p className="text-[13px] text-ink-2">
            This connects as yours — only you can ask questions using it.
          </p>
        )}

        {isSlack && isAdmin && (
          <p className="rounded-control bg-field px-3 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
            Want joel to answer @mentions in Slack? Configure the{" "}
            <Link
              href="/settings/slack"
              className="font-medium text-ink underline-offset-2 hover:underline"
              onClick={onClose}
            >
              Slack bot
            </Link>{" "}
            in Settings — separate from channel sync.
          </p>
        )}

        {def.job === "live" && (
          <p className="rounded-control bg-field px-3 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
            Live: used when someone asks a now-question. History is still
            indexed in this version. No write actions (create issue, etc.).
          </p>
        )}

        {inFlight && canManage && (
          <LoadingState
            label={`Syncing ${def.name}`}
            startedAt={card?.sync_started_at ?? jobs[0]?.started_at}
          />
        )}

        {connected && card && def.ingest && !inFlight && (
          jobsLoading ? (
            <LastPullSkeleton />
          ) : (
            <LastPull jobs={jobs} docCount={card.doc_count} />
          )
        )}

        {connected &&
          card?.error &&
          card.error !== jobs[0]?.error && (
            <p className="rounded-control bg-red-tint px-2.5 py-2 text-[12.5px] text-red">
              {card.error}
            </p>
          )}

        {connected && card && !canManage && (
          <p className="text-[13px] text-ink-2">
            Ask an admin to manage this connection.
          </p>
        )}

        {connected && card && def.ingest && canManage && (
          <>
            {isSlack && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[11.5px] font-medium text-ink-2">Channels</p>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      size="sm"
                      variant="primary"
                      onClick={() => {
                        pickedRef.current = true;
                        selectModeRef.current = "all";
                        setSelected(channels.map((channel) => channel.id));
                      }}
                    >
                      All
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="primary"
                      onClick={() => {
                        pickedRef.current = true;
                        selectModeRef.current = "none";
                        setSelected([]);
                      }}
                    >
                      None
                    </Button>
                  </div>
                </div>
                <div className="max-h-44 space-y-2 overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--line)] bg-inset p-3">
                  {channelsLoading ? (
                    <ChannelListSkeleton />
                  ) : channels.length === 0 ? (
                    <p className="text-[13px] text-ink-3">
                      {channelError ? "Could not list channels." : "No channels."}
                    </p>
                  ) : (
                    channels.map((channel) => (
                      <label
                        key={channel.id}
                        className="flex cursor-pointer items-center gap-2 text-[13px] text-ink"
                      >
                        <Checkbox
                          checked={selected.includes(channel.id)}
                          onChange={() => toggle(channel.id)}
                        />
                        <span>
                          #{channel.name}
                          {channel.is_private ? (
                            <span className="ml-1 text-ink-3">private</span>
                          ) : null}
                        </span>
                      </label>
                    ))
                  )}
                </div>
                {(live || inFlight) && (
                  <p className="text-[11.5px] text-ink-3">
                    Channel changes apply the next time you sync.
                  </p>
                )}
              </div>
            )}
            <Field label="How far back">
              <Select
                value={String(lookback)}
                onChange={(e) => {
                  const days = Number(e.target.value);
                  setLookback(days);
                  if (!needsSetup) onPatch({ lookback_days: days });
                }}
              >
                {LOOKBACK_OPTIONS.map((option) => (
                  <option key={option.days} value={option.days}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            {(live || inFlight) && (
              <Field label="How often">
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
            )}
          </>
        )}

        {connected && card && !def.ingest && (
          <p className="text-[13px] text-ink-3">
            Connected. Pulling from this tool isn’t available yet.
          </p>
        )}

        {connected && permissions}
      </div>

      {(primary || (connected && canManage)) && (
        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-line px-4 py-3">
          {connected && card && canManage ? (
            <button
              type="button"
              disabled={busy != null}
              onClick={onDisconnect}
              className="text-[13px] text-ink-3 hover:text-red disabled:opacity-40"
            >
              {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <span />
          )}
          {primary && (
            <Button
              type="button"
              variant={primary.variant}
              disabled={primary.disabled}
              loading={primary.loading}
              onClick={primary.onClick}
            >
              {primary.label}
            </Button>
          )}
        </div>
      )}
    </Dialog>
  );
}
