import type { ConnectorCard } from "./types";

export const SHIPPED_PROVIDERS = ["slack", "github", "gmail"] as const;

export const COMING_SOON_PROVIDERS = [
  "jira",
  "linear",
  "notion",
  "confluence",
  "googledrive",
  "hubspot",
  "fireflies",
] as const;

export const PROVIDER_META: Record<
  string,
  { label: string; blurb: string; icon: string; defaultInterval: number }
> = {
  slack: {
    label: "Slack",
    blurb: "Channels and threads — decisions, commitments, the hallway talk that never made it into a doc.",
    icon: "/icons/slack.svg",
    defaultInterval: 15,
  },
  github: {
    label: "GitHub",
    blurb: "Issues, PRs, and review comments — plus language-aware code chunks.",
    icon: "/icons/github.svg",
    defaultInterval: 30,
  },
  gmail: {
    label: "Gmail",
    blurb: "Mail threads that hold the real answer when the ticket just says 'see email'.",
    icon: "/icons/gmail.svg",
    defaultInterval: 20,
  },
  jira: {
    label: "Jira",
    blurb: "Coming soon",
    icon: "/icons/jira.svg",
    defaultInterval: 30,
  },
  linear: {
    label: "Linear",
    blurb: "Coming soon",
    icon: "/icons/linear.svg",
    defaultInterval: 30,
  },
  notion: {
    label: "Notion",
    blurb: "Coming soon",
    icon: "/icons/notion.svg",
    defaultInterval: 60,
  },
  confluence: {
    label: "Confluence",
    blurb: "Coming soon",
    icon: "/icons/confluence.svg",
    defaultInterval: 60,
  },
  googledrive: {
    label: "Google Drive",
    blurb: "Coming soon",
    icon: "/icons/googledrive.svg",
    defaultInterval: 60,
  },
  hubspot: {
    label: "HubSpot",
    blurb: "Coming soon",
    icon: "/icons/hubspot.svg",
    defaultInterval: 60,
  },
  fireflies: {
    label: "Fireflies",
    blurb: "Coming soon",
    icon: "/icons/fireflies.svg",
    defaultInterval: 60,
  },
};

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
