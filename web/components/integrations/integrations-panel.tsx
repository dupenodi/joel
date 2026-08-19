"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { IntegrationModal } from "@/components/integrations/integration-modal";
import { IntegrationTile } from "@/components/integrations/integration-tile";
import { Input } from "@/components/ui/input";
import {
  cancelConnector,
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
  INTEGRATIONS,
  type IntegrationDef,
  integrationIdFromParam,
  integrationLogoUrl,
  sortIntegrations,
} from "@/lib/integrations";
import type { ComposioStatus, ConnectorCard, JobRow } from "@/lib/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { IntegrationGridSkeleton } from "@/components/skeletons";
import { isSyncing } from "@/lib/connectors";

const ACTIVE = new Set(["ACTIVE", "SUCCESS", "CONNECTED"]);
const OPEN_KEY = "joel:open-integration";
const PANEL = "panel";

type BusyAction =
  | "connect"
  | "ingest"
  | "sync"
  | "cancel"
  | "disconnect"
  | "patch"
  | "key"
  | "clear";

function readOpenIntegration(): string | null {
  try {
    return integrationIdFromParam(sessionStorage.getItem(OPEN_KEY));
  } catch {
    return null;
  }
}

function writeOpenIntegration(id: string | null) {
  try {
    if (id) sessionStorage.setItem(OPEN_KEY, id);
    else sessionStorage.removeItem(OPEN_KEY);
  } catch {
    /* private mode */
  }
}

function friendlyError(raw: string): string {
  const msg = raw.trim();
  if (!msg) return "Something went wrong.";
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return "Can't reach the API. Is the local stack running?";
  }
  if (/already running/i.test(msg)) {
    return "Already pulling. Cancel first, or wait.";
  }
  if (/nothing to cancel/i.test(msg)) {
    return "Nothing to cancel.";
  }
  if (/access blocked|this app is blocked|this app tried to access sensitive/i.test(msg)) {
    return "Google blocked the app (extra scopes). Connect again — Gmail/Drive use gmail.readonly and drive.readonly only. If it still blocks, add your own OAuth client at composio.dev/auth/googleapps.";
  }
  try {
    return decodeURIComponent(msg.replace(/\+/g, " "));
  } catch {
    return msg;
  }
}

function isAuthError(raw: string | undefined): boolean {
  if (!raw) return false;
  return /401|unauthorized|invalid.{0,20}key|forbidden/i.test(raw);
}

export function IntegrationsPanel({
  surface,
}: {
  surface: "integrations" | "onboarding";
}) {
  const [composio, setComposio] = useState<ComposioStatus | null>(null);
  const [cards, setCards] = useState<ConnectorCard[]>([]);
  const [jobsById, setJobsById] = useState<Record<string, JobRow[]>>({});
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<Record<string, BusyAction>>({});
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const openIdRef = useRef(openId);
  openIdRef.current = openId;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const cardsRef = useRef(cards);
  cardsRef.current = cards;

  const refresh = useCallback(async () => {
    const [status, list] = await Promise.all([getComposio(), listConnectors()]);
    setComposio(status);
    setCards(list);
    const provider = openIdRef.current;
    const openCard = provider
      ? list.find((card) => card.provider === provider)
      : null;
    if (openCard?.id) {
      const jobs = await listJobs(openCard.id);
      setJobsById((current) => ({ ...current, [openCard.id!]: jobs }));
    }
    return { status, list };
  }, []);

  const loadJobs = useCallback(async (provider: string) => {
    const list = cardsRef.current;
    const openCard = list.find((card) => card.provider === provider);
    if (!openCard?.id) return;
    const jobs = await listJobs(openCard.id);
    setJobsById((current) => ({ ...current, [openCard.id!]: jobs }));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = integrationIdFromParam(params.get("connected"));
    const err = params.get("error") ?? params.get("error_description");
    const resume = connected ?? readOpenIntegration();
    if (err) setError(friendlyError(err));
    if (connected) writeOpenIntegration(connected);
    if (connected || err) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    if (resume) setOpenId(resume);
    refresh()
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [refresh, surface]);

  useEffect(() => {
    const id = setInterval(() => {
      const open = openIdRef.current;
      if (open && busyRef.current[open] === "connect") return;
      refresh().catch(() => {});
    }, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!openId) return;
    if (busyRef.current[openId] === "connect") return;
    loadJobs(openId).catch(() => {});
  }, [openId, loadJobs]);

  const configured = Boolean(composio?.configured);
  const keyRejected = isAuthError(composio?.error);
  const showKey = !configured || keyRejected;
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

  function setProviderBusy(id: string, action: BusyAction | null) {
    setBusy((current) => {
      if (action == null) {
        const next = { ...current };
        delete next[id];
        return next;
      }
      return { ...current, [id]: action };
    });
  }

  function markSyncing(provider: string) {
    const started = new Date().toISOString();
    setCards((list) =>
      list.map((card) =>
        card.provider === provider
          ? { ...card, status: "syncing", error: null, sync_started_at: started }
          : card,
      ),
    );
  }

  async function runProvider(
    provider: string,
    action: BusyAction,
    fn: () => Promise<void>,
  ) {
    setProviderBusy(provider, action);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? friendlyError(e.message) : "Action failed");
      await refresh().catch(() => {});
    } finally {
      setProviderBusy(provider, null);
    }
  }

  async function onSaveKey() {
    const trimmed = apiKey.trim();
    if (!trimmed) return;
    await runProvider(PANEL, "key", async () => {
      await setComposioKey(trimmed);
      setApiKey("");
    });
  }

  async function onClearKey() {
    await runProvider(PANEL, "clear", async () => {
      await setComposioKey(null);
    });
  }

  async function onConnect(def: IntegrationDef) {
    setProviderBusy(def.id, "connect");
    setError(null);
    writeOpenIntegration(def.id);
    try {
      const { redirect_url } = await connectComposioToolkit({
        toolkit: def.toolkit,
        returnTo: surface === "onboarding" ? "onboarding" : "integrations",
      });
      window.location.assign(redirect_url);
    } catch (e) {
      setProviderBusy(def.id, null);
      setError(e instanceof Error ? friendlyError(e.message) : "Action failed");
    }
  }

  const tiles = sortIntegrations(INTEGRATIONS, (def) => {
    const card = cards.find((item) => item.provider === def.id);
    const connected = Boolean(card?.id || accountByToolkit.get(def.toolkit));
    if (card?.status === "needs_reauth" || card?.error) return 0;
    if (isSyncing(card?.status)) return 1;
    if (connected) return 2;
    if (!def.connectable) return 4;
    return 3;
  });

  const closeModal = useCallback(() => {
    const open = openIdRef.current;
    if (open && busyRef.current[open] === "connect") return;
    writeOpenIntegration(null);
    setOpenId(null);
    setError(null);
  }, []);

  const panelBusy = busy[PANEL] ?? null;
  const openBusy = openId ? (busy[openId] ?? null) : null;

  return (
    <div className="space-y-6">
      {showKey && !loading && (
        <div className="flex flex-col gap-3 rounded-card bg-surface p-4 shadow-card sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1 space-y-1.5">
            <p className="text-[14px] font-medium text-ink">Composio API key</p>
            <p className="text-[13px] leading-relaxed text-ink-2">
              Required to connect tools.{" "}
              <a
                href="https://dashboard.composio.dev"
                target="_blank"
                rel="noreferrer"
                className="text-accent-ink underline-offset-2 hover:underline"
              >
                Get a key
              </a>
            </p>
            {keyRejected && (
              <p className="text-[13px] text-red">
                Composio rejected this key.
              </p>
            )}
            {error && !openId && (
              <p className="text-[13px] text-red">{error}</p>
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
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button
              type="button"
              size="sm"
              variant="accent"
              disabled={!apiKey.trim() || panelBusy != null}
              loading={panelBusy === "key"}
              onClick={() => void onSaveKey()}
            >
              Save key
            </Button>
            {configured && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={panelBusy != null}
                loading={panelBusy === "clear"}
                onClick={() => void onClearKey()}
              >
                Clear
              </Button>
            )}
          </div>
        </div>
      )}

      {error && !openId && !showKey && (
        <p className="text-[13px] text-red">{error}</p>
      )}

      {loading ? (
        <IntegrationGridSkeleton />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tiles.map((def) => {
            const card = cards.find((item) => item.provider === def.id);
            const account = accountByToolkit.get(def.toolkit);
            const connected = Boolean(card?.id || account);
            return (
              <IntegrationTile
                key={def.id}
                name={def.name}
                logoUrl={integrationLogoUrl(def.toolkit)}
                status={
                  card?.status ?? (connected ? "ready" : "pending_auth")
                }
                identity={account?.label ?? null}
                comingSoon={!def.connectable}
                attention={card?.error ?? null}
                docCount={card?.doc_count}
                lastSyncAt={card?.last_sync_at}
                syncStartedAt={card?.sync_started_at}
                onClick={() => setOpenId(def.id)}
              />
            );
          })}
        </div>
      )}

      {openDef && (
        <IntegrationModal
          key={openDef.id}
          open
          onClose={closeModal}
          def={openDef}
          card={openCard}
          jobs={openCard?.id ? (jobsById[openCard.id] ?? []) : []}
          jobsLoading={Boolean(openCard?.id) && jobsById[openCard.id] === undefined}
          connected={Boolean(openCard?.id || accountByToolkit.get(openDef.toolkit))}
          identity={accountByToolkit.get(openDef.toolkit)?.label ?? null}
          configured={configured}
          busy={openBusy}
          error={error}
          onConnect={() => void onConnect(openDef)}
          onStartIngest={({ lookbackDays, channelIds }) => {
            if (!openCard?.id) return;
            const connectorId = openCard.id;
            const provider = openDef.id;
            markSyncing(provider);
            void runProvider(provider, "ingest", async () => {
              await patchConnector(connectorId, {
                lookback_days: lookbackDays,
                channel_ids: channelIds,
              });
              await syncConnector(connectorId);
            });
          }}
          onSync={() => {
            if (!openCard?.id) return;
            markSyncing(openDef.id);
            void runProvider(openDef.id, "sync", async () => {
              await syncConnector(openCard.id!);
            });
          }}
          onCancel={() => {
            if (!openCard?.id) return;
            void runProvider(openDef.id, "cancel", async () => {
              await cancelConnector(openCard.id!);
            });
          }}
          onDisconnect={() => {
            if (!openCard?.id) return;
            void runProvider(openDef.id, "disconnect", async () => {
              await disconnectConnector(openCard.id!);
              writeOpenIntegration(null);
              setOpenId(null);
            });
          }}
          onPatch={(body) => {
            if (!openCard?.id) return;
            void runProvider(openDef.id, "patch", async () => {
              await patchConnector(openCard.id!, body);
            });
          }}
        />
      )}
    </div>
  );
}
