/** Joel’s integration allowlist — not Composio’s full catalog. */

export type IntegrationGroup =
  | "chat"
  | "code"
  | "mail"
  | "tracker"
  | "docs"
  | "crm"
  | "meetings";

export type IntegrationDef = {
  id: string;
  toolkit: string;
  name: string;
  group: IntegrationGroup;
  connectable: boolean;
  ingest: boolean;
  /** OAuth scopes actually requested. */
  permissions: string[];
  /** Constraint that isn’t a scope string (e.g. no DMs). */
  permissionNote?: string;
  defaultLookbackDays: number;
  defaultIntervalMin: number;
};

/** Talk → mail → code → tracker → docs → CRM → meetings. */
export const INTEGRATIONS: IntegrationDef[] = [
  {
    id: "slack",
    toolkit: "slack",
    name: "Slack",
    group: "chat",
    connectable: true,
    ingest: true,
    permissions: [
      "channels:read",
      "channels:history",
      "groups:read",
      "groups:history",
      "users:read",
    ],
    permissionNote: "No DMs (no im:history).",
    defaultLookbackDays: 30,
    defaultIntervalMin: 15,
  },
  {
    id: "gmail",
    toolkit: "gmail",
    name: "Gmail",
    group: "mail",
    connectable: true,
    ingest: true,
    permissions: ["gmail.readonly"],
    defaultLookbackDays: 30,
    defaultIntervalMin: 20,
  },
  {
    id: "github",
    toolkit: "github",
    name: "GitHub",
    group: "code",
    connectable: true,
    ingest: true,
    permissions: ["repo"],
    permissionNote: "Issues, PRs, review comments, and file contents.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 30,
  },
  {
    id: "linear",
    toolkit: "linear",
    name: "Linear",
    group: "tracker",
    connectable: true,
    ingest: true,
    permissions: ["read"],
    permissionNote: "Issues and comments.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 30,
  },
  {
    id: "notion",
    toolkit: "notion",
    name: "Notion",
    group: "docs",
    connectable: true,
    ingest: true,
    permissions: ["read"],
    permissionNote: "Pages the connected account can already open.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
  {
    id: "googledrive",
    toolkit: "googledrive",
    name: "Google Drive",
    group: "docs",
    connectable: true,
    ingest: true,
    permissions: ["drive.readonly"],
    permissionNote: "Docs, text files, and PDFs.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
  {
    id: "jira",
    toolkit: "jira",
    name: "Jira",
    group: "tracker",
    connectable: true,
    ingest: true,
    permissions: ["read:jira-work"],
    permissionNote: "Issues and comments.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 30,
  },
  {
    id: "confluence",
    toolkit: "confluence",
    name: "Confluence",
    group: "docs",
    connectable: true,
    ingest: true,
    permissions: ["read:confluence-content.all"],
    permissionNote: "Spaces and pages the connected account can already open.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
  {
    id: "hubspot",
    toolkit: "hubspot",
    name: "HubSpot",
    group: "crm",
    connectable: true,
    ingest: true,
    permissions: ["crm.objects.deals.read"],
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
  {
    id: "fireflies",
    toolkit: "fireflies",
    name: "Fireflies",
    group: "meetings",
    connectable: true,
    ingest: true,
    permissions: ["read"],
    permissionNote: "Meeting transcripts.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
];

export const INTEGRATION_BY_ID = Object.fromEntries(
  INTEGRATIONS.map((item) => [item.id, item]),
) as Record<string, IntegrationDef>;

export const GROUP_ORDER: IntegrationGroup[] = [
  "chat",
  "code",
  "mail",
  "tracker",
  "docs",
  "crm",
  "meetings",
];

export function integrationGroupLabel(group: IntegrationGroup): string {
  switch (group) {
    case "chat":
      return "Chat";
    case "code":
      return "Code";
    case "mail":
      return "Mail";
    case "tracker":
      return "Trackers";
    case "docs":
      return "Docs";
    case "crm":
      return "CRM";
    case "meetings":
      return "Meetings";
  }
}

export function integrationLogoUrl(toolkitSlug: string): string {
  return `https://logos.composio.dev/api/${encodeURIComponent(toolkitSlug)}`;
}

export function integrationIdFromParam(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const needle = raw.trim().toLowerCase();
  const hit = INTEGRATIONS.find(
    (item) => item.id === needle || item.toolkit === needle,
  );
  return hit?.id ?? null;
}

/** Attention first, then live, then the rest in catalog order. */
export function sortIntegrations<T extends { id: string; connectable: boolean }>(
  items: T[],
  rank: (item: T) => number,
): T[] {
  const index = new Map(items.map((item, i) => [item.id, i]));
  return [...items].sort((a, b) => {
    const d = rank(a) - rank(b);
    if (d !== 0) return d;
    return (index.get(a.id) ?? 0) - (index.get(b.id) ?? 0);
  });
}

export const LOOKBACK_OPTIONS = [
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 365, label: "Last year" },
] as const;

export const INTERVAL_OPTIONS = [
  { minutes: 15, label: "Every 15 minutes" },
  { minutes: 30, label: "Every 30 minutes" },
  { minutes: 60, label: "Every hour" },
] as const;
