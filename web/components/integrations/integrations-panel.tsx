"use client";

import { Banner } from "@/components/banner";
import { IntegrationModal } from "@/components/integrations/integration-modal";
import { IntegrationRow } from "@/components/integrations/integration-row";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  connectComposioToolkit,
  disconnectConnector,
  getComposio,
  listConnectors,
  listJobs,
  patchConnector,
  setComposioKey,
  syncConnector,
} from "@/lib/api";
import {
  GROUP_ORDER,
  INTEGRATIONS,
  type IntegrationDef,
  integrationGroupLabel,
  integrationLogoUrl,
} from "@/lib/integrations";
import type { ComposioStatus, ConnectorCard, JobRow } from "@/lib/types";
import { useCallback, useEffect, useMemo, useState } from "react";

const ACTIVE = new Set(["ACTIVE", "SUCCESS", "CONNECTED"]);

function friendlyError(raw: string): string {
  const msg = raw.trim();
  if (!msg) return "Something went wrong.";
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return "Can't reach the API. Is the local stack running?";
  }
  if (/access blocked|this app is blocked|this app tried to access sensitive/i.test(msg)) {
    return "Google blocked the Gmail/Drive app because extra scopes were requested. Click Connect again — Joel now uses readonly Gmail/Drive only. If Google still blocks, add your own Google OAuth client at composio.dev/auth/googleapps (testing mode, your email as a test user).";
  }
  try {
    return decodeURIComponent(msg.replace(/\+/g, " "));
  } catch {
    return msg;
  }
}

export function IntegrationsPanel({
  surface,
  onFirstIngest,
}: {
  surface: "connectors" | "onboarding";
  onFirstIngest?: () => void;
}) {
  const [composio, setComposio] = useState<ComposioStatus | null>(null);
  const [cards, setCards] = useState<ConnectorCard[]>([]);
  const [jobsById, setJobsById] = useState<Record<string, JobRow[]>>({});
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [status, list] = await Promise.all([getComposio(), listConnectors()]);
    setComposio(status);
    setCards(list);
    const connected = list.filter((card) => card.id);
    const entries = await Promise.all(
      connected.map(async (card) => [card.id!, await listJobs(card.id!)] as const),
    );
    setJobsById(Object.fromEntries(entries));
    if (status.error) setError(friendlyError(status.error));
    return { status, list };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const err = params.get("error") ?? params.get("error_description");
    if (connected) setToast(`${connected} connected.`);
    if (err) setError(friendlyError(err));
    if (connected || err) {
      const path = surface === "onboarding" ? "/onboarding" : "/connectors";
      window.history.replaceState({}, "", path);
    }
    refresh()
      .then(({ list }) => {
        if (connected) setOpenId(connected);
        const ready = list.find(
          (card) =>
            card.id &&
            card.ingest &&
            (card.status === "backfilling" ||
              card.status === "syncing" ||
              card.checklist?.fetched),
        );
        if (ready) onFirstIngest?.();
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [onFirstIngest, refresh, surface]);

  useEffect(() => {
    const id = setInterval(() => {
      refresh().catch(() => {});
    }, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  const configured = Boolean(composio?.configured);
  const openDef = INTEGRATIONS.find((item) => item.id === openId) ?? null;
  const openCard = cards.find((card) => card.provider === openId) ?? null;

  const accountByToolkit = useMemo(() => {
    const map = new Map<string, NonNullable<ComposioStatus["accounts"]>[number]>();
    for (const account of composio?.accounts ?? []) {
      if (ACTIVE.has(account.status.toUpperCase())) {
        map.set(account.toolkit, account);
      }
    }
    return map;
  }, [composio]);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? friendlyError(e.message) : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function onSaveKey() {
    const trimmed = apiKey.trim();
    if (!trimmed) return;
    await run("key", async () => {
      await setComposioKey(trimmed);
      setApiKey("");
      setToast("API key saved.");
    });
  }

  async function onClearKey() {
    await run("clear", async () => {
      await setComposioKey(null);
      setToast("API key cleared.");
    });
  }

  async function onConnect(def: IntegrationDef) {
    await run("connect", async () => {
      const { redirect_url } = await connectComposioToolkit({
        toolkit: def.toolkit,
        returnTo: surface === "onboarding" ? "onboarding" : "connectors",
      });
      window.location.assign(redirect_url);
    });
  }

  const groups = GROUP_ORDER.map((group) => ({
    group,
    label: integrationGroupLabel(group),
    items: INTEGRATIONS.filter((item) => item.group === group),
  }));

  return (
    <div className="space-y-8">
      {error && (
        <Banner tone="accent" className="rounded-[var(--radius-sm)]">
          {error}
        </Banner>
      )}
      {toast && (
        <Banner tone="ok" className="rounded-[var(--radius-sm)]">
          {toast}
        </Banner>
      )}

      <Surface elevation="raised" className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.06em] text-muted">
              Connections
            </p>
            <h2 className="mt-1 text-lg font-medium">Composio API key</h2>
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">
              One key. Then Connect on a tool. Auth happens in Composio; Joel
              still fetches and stores the docs.
            </p>
            <p className="mt-2 text-sm">
              <a
                href="https://dashboard.composio.dev"
                target="_blank"
                rel="noreferrer"
                className="text-ink underline underline-offset-2"
              >
                How to get a key
              </a>
            </p>
          </div>
          {composio?.key_source === "env" ? (
            <span className="text-xs text-muted">From environment</span>
          ) : configured ? (
            <span className="text-xs text-[var(--ok)]">Key saved</span>
          ) : null}
        </div>
        {composio?.masked_key && (
          <p className="font-mono text-sm text-muted">{composio.masked_key}</p>
        )}
        <Input
          type="password"
          placeholder="ak_…"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void onSaveKey();
          }}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={!apiKey.trim() || busy != null}
            loading={busy === "key"}
            onClick={() => void onSaveKey()}
          >
            Save key
          </Button>
          {configured && composio?.key_source === "settings" && (
            <Button
              type="button"
              size="sm"
              variant="soft"
              disabled={busy != null}
              loading={busy === "clear"}
              onClick={() => void onClearKey()}
            >
              Clear
            </Button>
          )}
        </div>
      </Surface>

      {loading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : (
        groups.map(({ group, label, items }) => (
          <section key={group} className="space-y-3">
            <div>
              <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted">
                {label}
              </h2>
              <p className="mt-1 text-sm text-ink-soft">
                  {group === "chat"
                    ? "Channels, then ingest."
                    : "Connect, then pick a lookback and ingest."}
              </p>
            </div>
            <ul className="space-y-2">
              {items.map((def) => {
                const card = cards.find((item) => item.provider === def.id);
                const account = accountByToolkit.get(def.toolkit);
                const connected = Boolean(card?.id || account);
                return (
                  <IntegrationRow
                    key={def.id}
                    name={def.name}
                    logoUrl={integrationLogoUrl(def.toolkit)}
                    scope={def.scope}
                    connected={connected}
                    identity={account?.label ?? null}
                    comingSoon={!def.connectable}
                    attention={card?.error ?? null}
                    onClick={() => setOpenId(def.id)}
                  />
                );
              })}
            </ul>
          </section>
        ))
      )}

      {openDef && (
        <IntegrationModal
          key={openDef.id}
          open
          onClose={() => setOpenId(null)}
          def={openDef}
          card={openCard}
          jobs={openCard?.id ? (jobsById[openCard.id] ?? []) : []}
          connected={Boolean(openCard?.id || accountByToolkit.get(openDef.toolkit))}
          identity={accountByToolkit.get(openDef.toolkit)?.label ?? null}
          configured={configured}
          busy={busy}
          error={error}
          onConnect={() => void onConnect(openDef)}
          onStartIngest={({ lookbackDays, channelIds }) => {
            if (!openCard?.id) return;
            void run("ingest", async () => {
              await patchConnector(openCard.id!, {
                lookback_days: lookbackDays,
                channel_ids: channelIds,
              });
              await syncConnector(openCard.id!);
              onFirstIngest?.();
            });
          }}
          onSync={() => {
            if (!openCard?.id) return;
            void run("sync", async () => {
              await syncConnector(openCard.id!);
            });
          }}
          onDisconnect={() => {
            if (!openCard?.id) return;
            void run("disconnect", async () => {
              await disconnectConnector(openCard.id!);
              setOpenId(null);
              setToast(`${openDef.name} disconnected.`);
            });
          }}
          onPatch={(body) => {
            if (!openCard?.id) return;
            void run("patch", async () => {
              await patchConnector(openCard.id!, body);
            });
          }}
        />
      )}
    </div>
  );
}
