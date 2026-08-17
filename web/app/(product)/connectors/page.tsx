"use client";

import { ConnectorCard } from "@/components/connector-card";
import { JobHistoryRow } from "@/components/job-row";
import { PageHeader } from "@/components/page-header";
import {
  connectProvider,
  disconnectConnector,
  listConnectors,
  listJobs,
  patchConnector,
  syncConnector,
} from "@/lib/api";
import type { ConnectorCard as ConnectorCardType, JobRow } from "@/lib/types";
import { useCallback, useEffect, useState } from "react";

export default function ConnectorsPage() {
  const [cards, setCards] = useState<ConnectorCardType[]>([]);
  const [jobsById, setJobsById] = useState<Record<string, JobRow[]>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const list = await listConnectors();
    setCards(list);
    const connected = list.filter((c) => c.id);
    const entries = await Promise.all(
      connected.map(async (c) => [c.id!, await listJobs(c.id!)] as const),
    );
    setJobsById(Object.fromEntries(entries));
  }, []);

  useEffect(() => {
    refresh().catch((e) =>
      setError(e instanceof Error ? e.message : "Failed to load"),
    );
    const id = setInterval(() => {
      refresh().catch(() => {});
    }, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  const live = cards.filter((c) => !c.coming_soon);
  const soon = cards.filter((c) => c.coming_soon);

  async function run(id: string | null, fn: () => Promise<void>) {
    setError(null);
    setBusyId(id ?? "x");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <PageHeader
        title="Connectors"
        description="Connect tools, watch sync status, and keep history walking backwards."
      />
      {error && <p className="mb-4 text-sm text-accent">{error}</p>}

      <section className="space-y-3">
        {live.map((card) => (
          <div key={card.provider} className="space-y-2">
            <ConnectorCard
              card={card}
              busy={busyId === card.id || busyId === card.provider}
              onConnect={() =>
                void run(card.provider, async () => {
                  await connectProvider(card.provider, "composio");
                })
              }
              onSync={() =>
                void run(card.id, async () => {
                  if (card.id) await syncConnector(card.id);
                })
              }
              onPause={() =>
                void run(card.id, async () => {
                  if (card.id) await patchConnector(card.id, { paused: true });
                })
              }
              onDisconnect={() =>
                void run(card.id, async () => {
                  if (card.id) await disconnectConnector(card.id);
                })
              }
              onReconnect={() =>
                void run(card.id, async () => {
                  if (card.id) await disconnectConnector(card.id);
                  await connectProvider(card.provider, "composio");
                })
              }
            />
            {card.id && (jobsById[card.id]?.length ?? 0) > 0 && (
              <details className="rounded-[var(--radius)] border border-[var(--line)] bg-surface px-4 py-3">
                <summary className="cursor-pointer text-sm text-ink-soft">
                  Job history ({jobsById[card.id].length})
                </summary>
                <div className="mt-2">
                  {jobsById[card.id].map((job) => (
                    <JobHistoryRow key={job.id} job={job} />
                  ))}
                </div>
              </details>
            )}
          </div>
        ))}
      </section>

      <section className="mt-12">
        <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.06em] text-muted">
          Coming soon
        </h2>
        <div className="grid gap-2 sm:grid-cols-2">
          {soon.map((card) => (
            <ConnectorCard key={card.provider} card={card} />
          ))}
        </div>
      </section>
    </div>
  );
}
