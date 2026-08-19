import type { ConnectorCard, ConnectorStatus } from "./types";
import { INTEGRATIONS } from "./integrations";

export const SYNCING_STATUSES: ReadonlySet<ConnectorStatus> = new Set([
  "backfilling",
  "syncing",
  "distilling",
  "linking",
]);

export function isSyncing(status: ConnectorStatus | undefined | null): boolean {
  return status != null && SYNCING_STATUSES.has(status);
}

/** §11.3: providers with a real backward-walking deep-backfill pass, kept
 * in sync with `DEEP_BACKFILL_PROVIDERS` in api/joel/app.py. Every other
 * provider's `backfill_done` is `true` the moment its first (and only)
 * sync completes -- true but not "full history," so the UI must not claim
 * that for them. */
export const DEEP_BACKFILL_PROVIDERS: ReadonlySet<string> = new Set(["slack", "gmail"]);

/** Pipeline stages collapse to one user-facing state. */
export function surfaceStatus(status: ConnectorStatus): ConnectorStatus {
  return isSyncing(status) ? "syncing" : status;
}

/** Ids that have a fetcher. Derived from the allowlist so this cannot drift. */
export const SHIPPED_PROVIDERS = INTEGRATIONS.filter((item) => item.ingest).map(
  (item) => item.id,
);

export const COMING_SOON_PROVIDERS = INTEGRATIONS.filter(
  (item) => !item.connectable,
).map((item) => item.id);

const BLURBS: Record<string, string> = {
  slack: "Channels you pick, plus threads. No DMs.",
  github: "Issues, PRs, review comments, and file contents.",
  gmail: "Mail threads (gmail.readonly).",
  jira: "Issues and comments.",
  linear: "Issues and comments.",
  notion: "Pages the connected account can already open.",
  confluence: "Spaces and pages the connected account can already open.",
  googledrive: "Docs, text files, and PDFs (drive.readonly).",
  hubspot: "Deals in pipelines the connected account can already open.",
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
      blurb: BLURBS[item.id] ?? item.permissionNote ?? item.permissions.join(" "),
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
