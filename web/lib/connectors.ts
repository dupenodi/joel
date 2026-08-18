import type { ConnectorCard } from "./types";
import { INTEGRATIONS } from "./integrations";

/** Ids that have a fetcher. Derived from the allowlist so this cannot drift. */
export const SHIPPED_PROVIDERS = INTEGRATIONS.filter((item) => item.ingest).map(
  (item) => item.id,
);

export const COMING_SOON_PROVIDERS = INTEGRATIONS.filter(
  (item) => !item.connectable,
).map((item) => item.id);

const BLURBS: Record<string, string> = {
  slack:
    "Channels and threads — decisions, commitments, the hallway talk that never made it into a doc.",
  github: "Issues, PRs, review comments, and language-aware code chunks.",
  gmail:
    "Mail threads that hold the real answer when the ticket just says 'see email'.",
  jira: "Issues and comments.",
  linear: "Issues and comments.",
  notion: "Pages you’re authorized for.",
  confluence: "Spaces and pages you’re authorized for.",
  googledrive: "Docs, text files, and PDFs you’re authorized for.",
  hubspot: "Deals in pipelines you’re authorized for.",
  fireflies: "Meeting transcripts.",
};

export const PROVIDER_META: Record<
  string,
  { label: string; blurb: string; icon: string; defaultInterval: number }
> = Object.fromEntries(
  INTEGRATIONS.map((item) => [
    item.id,
    {
      label: item.name,
      blurb: BLURBS[item.id] ?? item.scope,
      icon: `/icons/${item.id}.svg`,
      defaultInterval: item.defaultIntervalMin,
    },
  ]),
);

export function emptyConnectorCards(): ConnectorCard[] {
  const shipped = SHIPPED_PROVIDERS.map((provider) => ({
    id: null as string | null,
    provider,
    label: PROVIDER_META[provider].label,
    status: "pending_auth" as const,
    mode: null,
    doc_count: 0,
    last_sync_at: null,
    next_sync_at: null,
    backfill_done: false,
    backfill_progress: null,
    error: null,
    interval_min: PROVIDER_META[provider].defaultInterval,
    coming_soon: false,
  }));

  const soon = COMING_SOON_PROVIDERS.map((provider) => ({
    id: null as string | null,
    provider,
    label: PROVIDER_META[provider].label,
    status: "coming_soon" as const,
    mode: null,
    doc_count: 0,
    last_sync_at: null,
    next_sync_at: null,
    backfill_done: false,
    backfill_progress: null,
    error: null,
    interval_min: PROVIDER_META[provider].defaultInterval,
    coming_soon: true,
  }));

  return [...shipped, ...soon];
}

export function deriveOrgName(domain: string): string {
  const host = domain.replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
  const base = host.replace(/^www\./, "").split(".")[0] ?? host;
  return base.charAt(0).toUpperCase() + base.slice(1);
}

export function faviconUrl(domain: string): string {
  const host = domain.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=128`;
}
