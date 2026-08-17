import { BrandMark } from "@/components/brand-mark";
import { Banner } from "@/components/banner";
import { Checklist } from "@/components/checklist";
import { CitationChip } from "@/components/citation-chip";
import { ConnectorCard } from "@/components/connector-card";
import { ConversationItem } from "@/components/conversation-item";
import { EmptyState } from "@/components/empty-state";
import { Field } from "@/components/field";
import { JobHistoryRow } from "@/components/job-row";
import { MessageList } from "@/components/message-bubble";
import { OrgCard } from "@/components/org-card";
import { PageHeader } from "@/components/page-header";
import { ChatComposer } from "@/components/chat-composer";
import { Stat } from "@/components/stat";
import { StepIndicator } from "@/components/step-indicator";
import { AnswerBadge, StatusPill } from "@/components/status-pill";
import { Surface } from "@/components/surface";
import {
  Avatar,
  Badge,
  Button,
  Checkbox,
  Chip,
  IconButton,
  Input,
  Kbd,
  Progress,
  Select,
  Separator,
  Skeleton,
  Spinner,
  Switch,
  Textarea,
} from "@/components/ui";
import { emptyConnectorCards } from "@/lib/connectors";
import type { ConnectorCard as ConnectorCardType, JobRow, Message } from "@/lib/types";
import { Plus } from "lucide-react";

const mockConnectors: ConnectorCardType[] = emptyConnectorCards().map((c, i) => {
  if (c.provider === "slack") {
    return {
      ...c,
      id: "conn_slack",
      mode: "composio",
      status: "ready",
      doc_count: 1284,
      last_sync_at: new Date(Date.now() - 12 * 60_000).toISOString(),
      next_sync_at: new Date(Date.now() + 8 * 60_000).toISOString(),
      backfill_done: false,
      backfill_progress: 0.42,
    };
  }
  if (c.provider === "github") {
    return {
      ...c,
      id: "conn_gh",
      mode: "oauth",
      status: "needs_reauth",
      doc_count: 310,
      last_sync_at: new Date(Date.now() - 86_400_000).toISOString(),
      error: "refresh_token rejected — reconnect required",
    };
  }
  if (i === 0) return c;
  return c;
});

const mockJobs: JobRow[] = [
  {
    id: "j1",
    started_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    finished_at: new Date(Date.now() - 10 * 60_000).toISOString(),
    status: "ok",
    new_count: 14,
    changed_count: 3,
    unchanged_count: 220,
    duration_ms: 82000,
    error: null,
  },
  {
    id: "j2",
    started_at: new Date(Date.now() - 86_400_000).toISOString(),
    finished_at: new Date(Date.now() - 86_300_000).toISOString(),
    status: "error",
    new_count: 0,
    changed_count: 0,
    unchanged_count: 0,
    duration_ms: 1400,
    error: "429 rate limited",
  },
];

const mockMessages: Message[] = [
  {
    id: "m1",
    role: "user",
    content: "Who owns the billing rewrite?",
    created_at: new Date().toISOString(),
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "Maya Chen owns the billing rewrite (decision in #eng-billing, Mar 2026). The earlier owner Alex was superseded.",
    status: "answered",
    citations: [
      {
        doc_id: "d1",
        title: "#eng-billing · decision",
        url: "#",
        live: false,
      },
      {
        doc_id: "d2",
        title: "PR #882 review",
        url: "#",
        live: true,
      },
    ],
    lanes: ["artifacts", "graph", "phrase"],
    reasoning_path: [
      "Maya Chen -[:OWNS]-> Billing rewrite",
      "Alex -[:OWNS]-> (superseded)",
    ],
    created_at: new Date().toISOString(),
  },
  {
    id: "m3",
    role: "assistant",
    content: "Not in the company's memory.",
    status: "absent",
    created_at: new Date().toISOString(),
  },
];

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4 border-b border-[var(--line)] pb-12 last:border-0">
      <h2 className="font-display text-xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

export default function UiGalleryPage() {
  return (
    <div className="min-h-full bg-bg">
      <div className="mx-auto max-w-3xl space-y-12 px-6 py-12">
        <header className="space-y-4">
          <BrandMark size={48} withWordmark />
          <PageHeader
            title="UI kit"
            description="Atomic → complex. Same paper/ink theme as the landing. Mock only — no behavior wired."
          />
        </header>

        <Section title="Atomic">
          <div className="flex flex-wrap items-center gap-3">
            <Button>Primary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="soft">Soft</Button>
            <Button variant="danger">Danger</Button>
            <Button size="sm">Small</Button>
            <Button size="lg">Large</Button>
            <IconButton aria-label="Add">
              <Plus size={16} />
            </IconButton>
            <Spinner />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Domain">
              <Input placeholder="yourco.dev" defaultValue="acme.dev" readOnly />
            </Field>
            <Field label="Model">
              <Select defaultValue="sonnet" disabled>
                <option value="sonnet">claude-sonnet-4.5</option>
                <option value="haiku">claude-haiku-4.5</option>
              </Select>
            </Field>
            <Field label="Notes" className="sm:col-span-2">
              <Textarea defaultValue="Mock notes" readOnly />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox defaultChecked readOnly /> Pause ingestion
            </label>
            <div className="flex items-center gap-2 text-sm">
              <Switch checked label="Sync enabled" /> Sync
            </div>
            <Avatar name="You" />
            <Avatar name="Acme" src="https://www.google.com/s2/favicons?domain=acme.com&sz=128" />
            <Kbd>⌘K</Kbd>
            <Chip>artifacts</Chip>
            <Chip active>graph</Chip>
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge>Neutral</Badge>
            <Badge tone="ink">Ink</Badge>
            <Badge tone="ok">Ok</Badge>
            <Badge tone="partial">Partial</Badge>
            <Badge tone="warn">Warn</Badge>
            <Badge tone="accent">Accent</Badge>
            <Badge tone="muted">Muted</Badge>
            <StatusPill status="ready" />
            <StatusPill status="backfilling" />
            <StatusPill status="needs_reauth" />
            <AnswerBadge status="answered" />
            <AnswerBadge status="absent" />
          </div>

          <Progress value={42} />
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
          <Separator />
        </Section>

        <Section title="Surfaces & chrome">
          <div className="grid gap-4 sm:grid-cols-3">
            <Surface elevation="flat">Flat</Surface>
            <Surface elevation="raised">Raised</Surface>
            <Surface elevation="hard">Hard offset</Surface>
          </div>
          <StepIndicator step={2} total={3} label="Step 2 of 3 — first tool" />
          <Banner tone="muted">Still ingesting — answers may be incomplete.</Banner>
          <Banner tone="accent">Slack needs reconnect.</Banner>
          <Banner tone="warn">Relationship search unavailable.</Banner>
        </Section>

        <Section title="Product blocks">
          <OrgCard
            name="Acme"
            domain="acme.dev"
            logoUrl="https://www.google.com/s2/favicons?domain=acme.dev&sz=128"
          />
          <Surface elevation="hard">
            <Checklist
              items={[
                { key: "a", label: "fetched", done: true },
                { key: "b", label: "distilled", done: true },
                { key: "c", label: "people resolved", done: false },
                { key: "d", label: "graph linked", done: false },
                { key: "e", label: "indexes consistent", done: false },
              ]}
            />
          </Surface>
          <div className="space-y-3">
            {mockConnectors
              .filter((c) => !c.coming_soon)
              .slice(0, 3)
              .map((card) => (
                <ConnectorCard key={card.provider} card={card} />
              ))}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {mockConnectors
              .filter((c) => c.coming_soon)
              .slice(0, 4)
              .map((card) => (
                <ConnectorCard key={card.provider} card={card} />
              ))}
          </div>
          <Surface>
            {mockJobs.map((job) => (
              <JobHistoryRow key={job.id} job={job} />
            ))}
          </Surface>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Docs" value={1284} />
            <Stat label="Artifacts" value={96} />
            <Stat label="Entities" value={214} />
            <Stat label="Index" value="consistent" />
          </dl>
        </Section>

        <Section title="Chat">
          <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-surface">
            <div className="flex min-h-[420px]">
              <aside className="hidden w-52 border-r border-[var(--line)] p-2 sm:block">
                <ConversationItem
                  conversation={{
                    id: "c1",
                    title: "Who owns the billing rewrite?",
                    created_at: new Date().toISOString(),
                  }}
                  active
                />
                <ConversationItem
                  conversation={{
                    id: "c2",
                    title: "What overturned the Q2 plan?",
                    created_at: new Date().toISOString(),
                  }}
                />
              </aside>
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex-1 overflow-auto p-5">
                  <MessageList messages={mockMessages} />
                </div>
                <ChatComposer value="What about the other one?" />
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <CitationChip
              citation={{
                doc_id: "x",
                title: "Sample citation",
                url: "#",
                live: false,
              }}
            />
          </div>
        </Section>

        <Section title="Empty">
          <EmptyState
            title="Chat needs memory first"
            description="Connect a tool and wait for the first connector to reach ready."
            action={<Button type="button">Go to onboarding</Button>}
          />
        </Section>
      </div>
    </div>
  );
}
