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
  scope: string;
  defaultLookbackDays: number;
  defaultIntervalMin: number;
};

export const INTEGRATIONS: IntegrationDef[] = [
  {
    id: "slack",
    toolkit: "slack",
    name: "Slack",
    group: "chat",
    connectable: true,
    ingest: true,
    scope: "Channels you pick, plus threads. No DMs.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 15,
  },
  {
    id: "github",
    toolkit: "github",
    name: "GitHub",
    group: "code",
    connectable: true,
    ingest: true,
    scope: "Issues, PRs, review comments, and language-aware code chunks.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 30,
  },
  {
    id: "gmail",
    toolkit: "gmail",
    name: "Gmail",
    group: "mail",
    connectable: true,
    ingest: true,
    scope: "Mail threads you’re authorized for.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 20,
  },
  {
    id: "linear",
    toolkit: "linear",
    name: "Linear",
    group: "tracker",
    connectable: true,
    ingest: true,
    scope: "Issues and comments.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 30,
  },
  {
    id: "jira",
    toolkit: "jira",
    name: "Jira",
    group: "tracker",
    connectable: true,
    ingest: true,
    scope: "Issues and comments.",
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
    scope: "Pages you’re authorized for.",
    defaultLookbackDays: 30,
    defaultIntervalMin: 60,
  },
  {
    id: "confluence",
    toolkit: "confluence",
    name: "Confluence",
    group: "docs",
    connectable: true,
    ingest: true,
    scope: "Spaces and pages you’re authorized for.",
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
    scope: "Docs, text files, and PDFs you’re authorized for.",
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
    scope: "Deals in pipelines you’re authorized for.",
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
    scope: "Meeting transcripts.",
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
