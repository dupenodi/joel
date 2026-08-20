"use client";

import {
  AnswerBadge,
  AnswerTurn,
  BuiButton,
  BuiScope,
  ChatPanel,
  CitationChip,
  CodeBlock,
  ConnectorStatus,
  ContextCards,
  ConversationList,
  InsightCards,
  LaneChips,
  LoadingState,
  LockedChat,
  MemoryBanner,
  MemoryConnector,
  PromptBar,
  ReadinessChecklist,
  SearchList,
  SidebarNav,
  StreamingText,
  TaskRows,
  ThinkingState,
  ToolChips,
  UserTurn,
} from "@/components/beautifului";
import type { ConnectorCard, Message } from "@/lib/types";
import { useState } from "react";

const NAV = [
  {
    label: "Brand",
    items: [
      ["principles", "Principles"],
      ["color", "Color"],
      ["type", "Type"],
      ["radius-shadow", "Radius & shadow"],
      ["motion", "Motion"],
    ],
  },
  {
    label: "Atoms",
    items: [
      ["button", "Button"],
      ["field", "Field"],
      ["chip", "Chip"],
      ["control", "Control"],
      ["status", "Status"],
    ],
  },
  {
    label: "Chat",
    items: [
      ["answer-turn", "Answer turn"],
      ["answer-badge", "Answer badge"],
      ["citation", "Citation"],
      ["conflict", "Conflict"],
      ["reasoning-path", "Reasoning path"],
      ["lanes", "Lanes"],
      ["thinking", "Thinking"],
      ["streaming-text", "Streaming text"],
      ["tool-chips", "Lookups"],
      ["prompt-bar", "Prompt bar"],
      ["chat", "Chat panel"],
      ["locked-chat", "Locked chat"],
    ],
  },
  {
    label: "Memory",
    items: [
      ["banners", "Banners"],
      ["context-cards", "Retrieved chunks"],
      ["conversations", "Conversations"],
      ["search", "Search"],
      ["sidebar-nav", "Sidebar"],
      ["loading-state", "Ingesting"],
    ],
  },
  {
    label: "Connectors",
    items: [
      ["connector", "Connector card"],
      ["sync-jobs", "Sync jobs"],
      ["readiness", "Readiness"],
    ],
  },
  {
    label: "Profile",
    items: [
      ["insight-cards", "Corpus"],
      ["code-block", "Cited code"],
    ],
  },
] as const;

const COLORS: { name: string; css: string; note: string }[] = [
  { name: "page", css: "var(--page)", note: "App ground" },
  { name: "canvas", css: "var(--canvas)", note: "Stage / well" },
  { name: "surface", css: "var(--surface)", note: "Card face" },
  { name: "inset", css: "var(--inset)", note: "Recessed fill" },
  { name: "hover", css: "var(--hover)", note: "Row hover" },
  { name: "hover-2", css: "var(--hover-2)", note: "Pressed hover" },
  { name: "ink", css: "var(--ink)", note: "Primary text" },
  { name: "ink-2", css: "var(--ink-2)", note: "Secondary" },
  { name: "ink-3", css: "var(--ink-3)", note: "Caption / idle" },
  { name: "line", css: "var(--line)", note: "Hairline" },
  { name: "line-strong", css: "var(--line-strong)", note: "Control ring" },
  { name: "field", css: "var(--field)", note: "Input fill" },
  { name: "accent", css: "var(--accent)", note: "Cobalt action" },
  { name: "accent-ink", css: "var(--accent-ink)", note: "Accent text" },
  { name: "accent-tint", css: "var(--accent-tint)", note: "Accent wash" },
  { name: "green", css: "var(--green)", note: "Done / add" },
  { name: "green-tint", css: "var(--green-tint)", note: "Done wash" },
  { name: "orange", css: "var(--orange)", note: "Review" },
  { name: "orange-tint", css: "var(--orange-tint)", note: "Review wash" },
  { name: "red", css: "var(--red)", note: "Fail / delete" },
  { name: "red-tint", css: "var(--red-tint)", note: "Fail wash" },
];

function VariantTabs({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (next: string) => void;
}) {
  return (
    <div className="mt-6 flex justify-center">
      <div className="flex items-center rounded-full bg-field p-0.5 shadow-hairline">
        {options.map((option) => {
          const active = option === value;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option)}
              className={`h-7 rounded-full px-3 text-[12.5px] font-medium transition-colors ${
                active
                  ? "bg-surface text-ink shadow-btn"
                  : "text-ink-2 hover:text-ink"
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Stage({
  id,
  kicker,
  title,
  description,
  wide,
  children,
}: {
  id: string;
  kicker?: string;
  title: string;
  description: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-8">
      <div className="mb-3 flex items-baseline gap-3">
        {kicker ? (
          <span className="font-mono text-[12px] text-ink-3">{kicker}</span>
        ) : null}
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight text-ink">
            {title}
          </h2>
          <p className="text-[13px] text-ink-2">{description}</p>
        </div>
      </div>
      <div
        className={`rounded-[16px] bg-canvas p-8 ${
          wide ? "" : "flex min-h-[220px] items-center justify-center"
        }`}
      >
        {children}
      </div>
    </section>
  );
}

function Meter({ signal, tone }: { signal: number; tone: string }) {
  return (
    <span className="flex items-end gap-0.5">
      {[0, 1, 2].map((bar) => (
        <span
          key={bar}
          className="w-1 rounded-full"
          style={{
            height: 10,
            background: bar < signal ? tone : "var(--line-strong)",
          }}
        />
      ))}
    </span>
  );
}

function BrandLanguage() {
  return (
    <>
      <Stage
        id="principles"
        title="Principles"
        description="Extracted from the scraped primitives — this is the product language, not a second theme."
        wide
      >
        <ul className="grid gap-3 sm:grid-cols-2">
          {[
            [
              "Cool paper",
              "Near-white page, a slightly cooler canvas well, white cards. No cream, no charcoal.",
            ],
            [
              "Ink ladder",
              "ink / ink-2 / ink-3. Captions never go to a fourth gray. Working labels shimmer between ink-3 and ink.",
            ],
            [
              "Cobalt, not red",
              "Accent is for live lookups, links, and selected tools. Green / orange / red are status only.",
            ],
            [
              "13px UI",
              "Body copy and controls are 13px. Secondary 12.5. Captions 11.5. Mono for numbers, files, code.",
            ],
            [
              "Concentric radius",
              "Chip 6 · control 8 · card 10. A 36px pill wraps 28px controls so the inner radius stays 14.",
            ],
            [
              "Hairline, then air",
              "Every surface is a 1px ring in line or line-strong, then a soft drop. No hard offset shadows.",
            ],
            [
              "Settle, don’t loop",
              "Traces and diffs play once. Working states shimmer; idle states stay still.",
            ],
            [
              "Ease out strong",
              "cubic-bezier(0.23, 1, 0.32, 1) for expand/collapse. 150ms for color. Pop-in from 0.95.",
            ],
          ].map(([title, body]) => (
            <li
              key={title}
              className="rounded-card bg-surface p-3 shadow-hairline"
            >
              <p className="text-[13px] font-semibold text-ink">{title}</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">
                {body}
              </p>
            </li>
          ))}
        </ul>
      </Stage>

      <Stage
        id="color"
        title="Color"
        description="Token names as used in components. Swatches inherit the live CSS variables."
        wide
      >
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {COLORS.map((c) => (
            <div
              key={c.name}
              className="overflow-hidden rounded-control bg-surface shadow-hairline"
            >
              <div className="h-12" style={{ background: c.css }} />
              <div className="px-2.5 py-2">
                <p className="font-mono text-[11.5px] font-medium text-ink">
                  {c.name}
                </p>
                <p className="text-[11.5px] text-ink-3">{c.note}</p>
              </div>
            </div>
          ))}
        </div>
      </Stage>

      <Stage
        id="type"
        title="Type"
        description="Satoshi on the Beautiful UI metric. 13px is the default, not 16."
        wide
      >
        <div className="space-y-4 rounded-card bg-surface p-4 shadow-hairline">
          {[
            ["15px semibold", "text-[15px] font-semibold tracking-tight", "Section title"],
            ["13px medium", "text-[13px] font-medium", "Control, body, nav item"],
            ["13px regular", "text-[13px]", "Streaming answer, table cell"],
            ["12.5px", "text-[12.5px] text-ink-2", "Secondary label, meter caption"],
            ["12px mono", "font-mono text-[12px] text-ink", "Filename, token, elapsed time"],
            ["11.5px", "text-[11.5px] text-ink-3", "Badge, copy button, chart tick"],
          ].map(([label, cls, sample]) => (
            <div
              key={label}
              className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line pb-3 last:border-0 last:pb-0"
            >
              <span className={cls}>{sample}</span>
              <span className="font-mono text-[11px] text-ink-3">{label}</span>
            </div>
          ))}
        </div>
      </Stage>

      <Stage
        id="radius-shadow"
        title="Radius & shadow"
        description="Three radii. Four elevations. Always a 1px ring first."
        wide
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex items-end gap-3">
            <div className="flex size-14 items-center justify-center rounded-chip bg-surface text-[11px] text-ink-2 shadow-hairline">
              6
            </div>
            <div className="flex size-16 items-center justify-center rounded-control bg-surface text-[11px] text-ink-2 shadow-btn">
              8
            </div>
            <div className="flex h-[72px] flex-1 items-center justify-center rounded-card bg-surface text-[11px] text-ink-2 shadow-card">
              10 card
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[
              ["hairline", "shadow-hairline"],
              ["btn", "shadow-btn"],
              ["card", "shadow-card"],
              ["raised", "shadow-raised"],
            ].map(([name, cls]) => (
              <div
                key={name}
                className={`flex h-16 items-center justify-center rounded-card bg-surface text-[12px] text-ink-2 ${cls}`}
              >
                {name}
              </div>
            ))}
          </div>
        </div>
      </Stage>

      <Stage
        id="motion"
        title="Motion"
        description="Working shimmers. Arrival pops. Expand uses grid-template-rows, not height."
        wide
      >
        <div className="flex flex-wrap items-center gap-8">
          <span
            className="bg-clip-text text-[13px] font-medium text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
              backgroundSize: "200% 100%",
              animation: "shimmer-text 1.4s linear infinite",
            }}
          >
            Thinking
          </span>
          <span
            className="rounded-card bg-surface px-3 py-2 text-[13px] text-ink shadow-card"
            style={{
              animation: "pop-in 220ms cubic-bezier(0.23,1,0.32,1) both",
            }}
          >
            pop-in
          </span>
          <span
            className="text-[13px] text-ink"
            style={{
              animation: "stream-in 420ms cubic-bezier(0.22,0.61,0.25,1) both",
            }}
          >
            stream-in
          </span>
          <span className="font-mono text-[11.5px] text-ink-3">
            150ms color · 300–400ms expand · ease-out-strong
          </span>
        </div>
      </Stage>
    </>
  );
}

function Atoms() {
  const [on, setOn] = useState(true);

  return (
    <>
      <Stage
        id="button"
        title="Button"
        description="28px default. Full radius. Accent is ink-on-canvas, not cobalt fill — cobalt is for links and AI chrome."
      >
        <div className="flex flex-wrap items-center gap-2">
          <BuiButton variant="accent" size="sm">
            Connect
          </BuiButton>
          <BuiButton variant="primary" size="sm">
            Sync now
          </BuiButton>
          <BuiButton variant="secondary" size="sm">
            Disconnect
          </BuiButton>
          <BuiButton variant="danger" size="sm">
            Reconnect
          </BuiButton>
          <BuiButton variant="accent" size="md">
            Send
          </BuiButton>
          <button
            type="button"
            className="primitive-icon-button text-ink-3 hover:bg-hover hover:text-ink"
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </Stage>

      <Stage
        id="field"
        title="Field"
        description="Transparent on hover-row. Hairline ring. 13px text. Placeholder is ink-3."
      >
        <div className="flex w-full max-w-sm flex-col gap-3">
          <label className="flex h-10 items-center gap-2 rounded-control bg-surface px-3 shadow-hairline">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              placeholder="Search memory…"
              className="min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-3"
            />
          </label>
          <input
            defaultValue="Type something…"
            className="h-8 rounded-control bg-transparent px-2 text-[13px] text-ink outline-none placeholder:text-ink-3 hover:bg-hover"
          />
        </div>
      </Stage>

      <Stage
        id="chip"
        title="Chip"
        description="Source chips and lane tokens. Height 20–28px. Never a pill taller than a control."
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-inset px-2 text-[12px] font-medium text-ink-2 shadow-btn">
            <span className="flex size-3.5 items-center justify-center rounded-[4px] bg-accent text-[7px] font-bold text-white">
              SL
            </span>
            #billing-owners
          </span>
          <code className="rounded-md bg-accent-tint px-1.5 py-0.5 font-mono text-[12px] text-accent-ink">
            graph
          </code>
          <span className="inline-flex h-7 items-center gap-1.5 rounded-chip bg-surface px-1.5 font-mono text-[11.5px] text-ink shadow-btn">
            billing.ts
          </span>
          <span className="inline-flex h-5 items-center rounded-md bg-inset px-1.5 text-[11.5px] font-medium text-ink-2 shadow-hairline tabular-nums">
            12
          </span>
        </div>
      </Stage>

      <Stage
        id="control"
        title="Control"
        description="Radios for lane choice. Switch for pause ingestion. Meter for rerank confidence."
      >
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            {["Graph + phrase", "All six lanes"].map((label, i) => {
              const selected = i === 0;
              return (
                <button
                  key={label}
                  type="button"
                  className="flex items-center gap-2 rounded-control px-1.5 py-1 text-left hover:bg-hover"
                >
                  <span
                    className={`flex size-4 items-center justify-center rounded-full ${
                      selected
                        ? "bg-ink text-canvas"
                        : "text-transparent shadow-[inset_0_0_0_1.5px_var(--line-strong)]"
                    }`}
                  >
                    <span className="size-1.5 rounded-full bg-canvas" />
                  </span>
                  <span className={`text-[13px] ${selected ? "text-ink" : "text-ink-2"}`}>
                    {label}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-3">
            <Meter signal={3} tone="var(--green)" />
            <span className="text-[12.5px] font-medium text-ink-2">High confidence</span>
            <Meter signal={2} tone="var(--orange)" />
            <span className="text-[12.5px] text-ink-3">Needs review</span>
            <Meter signal={0} tone="var(--ink-3)" />
            <span className="text-[12.5px] text-ink-3">No signal</span>
          </div>
          <button
            type="button"
            aria-pressed={on}
            onClick={() => setOn((v) => !v)}
            className={`relative h-5 w-9 rounded-full transition-colors ${
              on ? "bg-ink" : "bg-line-strong"
            }`}
          >
            <span
              className="absolute top-0.5 size-4 rounded-full bg-surface transition-transform"
              style={{ transform: on ? "translateX(18px)" : "translateX(2px)" }}
            />
          </button>
        </div>
      </Stage>

      <Stage
        id="status"
        title="Status"
        description="Answer honesty on the left. Connector machine on the right. Green / orange / red are status only."
      >
        <div className="flex flex-col items-start gap-3">
          <div className="flex flex-wrap gap-1.5">
            <AnswerBadge status="answered" />
            <AnswerBadge status="partial" />
            <AnswerBadge status="conflicted" />
            <AnswerBadge status="absent" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            <ConnectorStatus status="ready" />
            <ConnectorStatus status="syncing" />
            <ConnectorStatus status="distilling" />
            <ConnectorStatus status="needs_reauth" />
            <ConnectorStatus status="error" />
          </div>
        </div>
      </Stage>
    </>
  );
}

const TURNS: Record<string, Message> = {
  Answered: {
    role: "assistant",
    status: "answered",
    content:
      "Maya Chen owns billing after the Q3 reversal. The on-call rotation still lists her as of just now.",
    citations: [
      {
        doc_id: "slack-1",
        title: "#billing-owners",
        url: "https://slack.com/",
        live: false,
        provider: "slack",
      },
      {
        doc_id: "gmail-1",
        title: "On-call rotation",
        url: "https://mail.google.com/",
        live: true,
        provider: "gmail",
      },
    ],
    lanes: ["graph", "phrase", "live"],
    reasoning_path: [
      "Maya Chen -[:OWNS]-> Billing",
      "Priya Shah -[:OWNED]-> Billing  (2026-06-12, superseded)",
    ],
  },
  Partial: {
    role: "assistant",
    status: "partial",
    content:
      "Maya Chen owns billing. Backup on-call is not in the indexed threads.",
    not_found: ["billing backup on-call"],
    citations: [
      {
        doc_id: "gh-1",
        title: "RFC: billing ownership",
        url: "https://github.com/",
        live: false,
        provider: "github",
      },
    ],
    lanes: ["artifacts", "phrase"],
  },
  Conflicted: {
    role: "assistant",
    status: "conflicted",
    content: "Memory has two dated positions on who owns billing.",
    conflicts: [
      {
        assessment: "The September RFC supersedes the June Slack assignment.",
        positions: [
          {
            claim: "Priya Shah owns billing.",
            date: "12 Jun 2026",
            source: "#owners",
          },
          {
            claim: "Maya Chen owns billing.",
            date: "3 Sep 2026",
            source: "RFC #441",
          },
        ],
      },
    ],
    lanes: ["graph", "artifacts"],
  },
  Absent: {
    role: "assistant",
    status: "absent",
    content: "Not in the company's memory.",
  },
};

const SLACK_CARD: ConnectorCard = {
  id: "conn-slack",
  provider: "slack",
  label: "Slack",
  status: "ready",
  mode: "composio",
  doc_count: 12480,
  last_sync_at: "12m ago",
  next_sync_at: "in 18m",
  backfill_done: true,
  backfill_progress: 1,
  error: null,
  interval_min: 30,
  coming_soon: false,
};

function Components() {
  const [loader, setLoader] = useState("Drive");
  const [thinking, setThinking] = useState("Planning");
  const [tasks, setTasks] = useState("Capsules");
  const [turn, setTurn] = useState("Answered");
  const [thread, setThread] = useState("c1");

  return (
    <>
      <Stage
        id="answer-turn"
        kicker="01"
        title="Answer turn"
        description="The honesty contract: badge, body, conflict or gap, citations, reasoning path, lanes."
      >
        <div className="flex w-full max-w-lg flex-col gap-4">
          <UserTurn>Who owns billing after the Q3 reversal?</UserTurn>
          <AnswerTurn key={turn} message={TURNS[turn]} />
          <VariantTabs
            value={turn}
            options={["Answered", "Partial", "Conflicted", "Absent"]}
            onChange={setTurn}
          />
        </div>
      </Stage>

      <Stage
        id="answer-badge"
        title="Answer badge"
        description="Four resting states. Partial names the gap. Absent is a sentence, not a shrug."
      >
        <div className="flex flex-wrap gap-1.5">
          <AnswerBadge status="answered" />
          <AnswerBadge status="partial" />
          <AnswerBadge status="conflicted" />
          <AnswerBadge status="absent" />
        </div>
      </Stage>

      <Stage
        id="citation"
        title="Citation"
        description="Deep-link, LIVE mark for lookups."
      >
        <div className="flex flex-wrap gap-2">
          <CitationChip
            citation={{
              doc_id: "1",
              title: "#billing-owners",
              url: "https://slack.com/",
              live: false,
              provider: "slack",
            }}
          />
          <CitationChip
            citation={{
              doc_id: "2",
              title: "On-call rotation",
              url: "https://mail.google.com/",
              live: true,
              provider: "gmail",
            }}
          />
        </div>
      </Stage>

      <Stage
        id="conflict"
        title="Conflict"
        description="Two dated, sourced positions. One assessment line. Never blended."
      >
        <div className="w-full max-w-lg">
          <AnswerTurn message={TURNS.Conflicted} />
        </div>
      </Stage>

      <Stage
        id="reasoning-path"
        title="Reasoning path"
        description="The graph is the explorer — collapse it, don’t build a second page."
      >
        <div className="w-full max-w-md">
          <AnswerTurn
            message={{
              ...TURNS.Answered,
              content: "Maya Chen owns billing.",
            }}
          />
        </div>
      </Stage>

      <Stage
        id="lanes"
        title="Lanes"
        description="Which retrieval lanes contributed. Mono, quiet, footer of the turn."
      >
        <LaneChips lanes={["artifacts", "phrase", "graph", "live"]} />
      </Stage>

      <Stage
        id="thinking"
        title="Thinking"
        description="Agent actions — not exclusive modes. Planning, searching, relationships, live check."
      >
        <div className="flex w-full max-w-md flex-col">
          <ThinkingState key={thinking} variant={thinking} />
          <VariantTabs
            value={thinking}
            options={["Planning", "Searching", "Relationships", "Live"]}
            onChange={setThinking}
          />
        </div>
      </Stage>

      <Stage
        id="streaming-text"
        title="Streaming text"
        description="Tokens resolve out of blur. Inline cite, then sources and follow-ups."
      >
        <StreamingText />
      </Stage>

      <Stage
        id="tool-chips"
        title="Lookups"
        description="Read-only: plan, VECTOR, GRAPH, LIVE. Citations land when the run settles."
      >
        <ToolChips />
      </Stage>

      <Stage
        id="prompt-bar"
        title="Prompt bar"
        description="Question and send. No distill, slash commands, or source menus."
      >
        <div className="flex w-full max-w-lg flex-col">
          <PromptBar demo={false} placeholder="Ask a question…" />
        </div>
      </Stage>

      <Stage
        id="chat"
        title="Chat panel"
        description="Thread + composer. Tabs are memory vs live lookups, not workspaces."
      >
        <ChatPanel />
      </Stage>

      <Stage
        id="locked-chat"
        title="Locked chat"
        description="Empty chat is allowed. Connect tools when you're ready."
      >
        <LockedChat href="/integrations" />
      </Stage>

      <Stage
        id="banners"
        title="Banners"
        description="Ingesting, re-auth, degraded graph, LLM key, disk, graph rebuild."
        wide
      >
        <div className="flex flex-col gap-2">
          <MemoryBanner kind="ingesting" />
          <MemoryBanner
            kind="reauth"
            action={
              <a href="/integrations" className="font-medium underline-offset-2 hover:underline">
                Fix it
              </a>
            }
          >
            Slack needs reconnect.
          </MemoryBanner>
          <MemoryBanner kind="degraded" />
          <MemoryBanner kind="llm" />
        </div>
      </Stage>

      <Stage
        id="context-cards"
        title="Retrieved chunks"
        description="Distilled artifacts with their source, not raw chatter."
      >
        <ContextCards />
      </Stage>

      <Stage
        id="conversations"
        title="Conversations"
        description="Auto-titled from the first question. Quiet list, one active."
      >
        <ConversationList
          activeId={thread}
          onSelect={setThread}
          items={[
            { id: "c1", title: "Who owns billing", when: "12m ago" },
            { id: "c2", title: "On-call rotation", when: "Yesterday" },
            { id: "c3", title: "Q3 reversal note", when: "Mon" },
          ]}
        />
      </Stage>

      <Stage
        id="search"
        title="Search"
        description="Jump to a person, thread, doc, or connector."
      >
        <SearchList />
      </Stage>

      <Stage
        id="sidebar-nav"
        title="Sidebar"
        description="App pages plus recent threads."
      >
        <div className="h-[360px] w-full max-w-xs overflow-hidden rounded-[14px] bg-surface shadow-raised">
          <SidebarNav />
        </div>
      </Stage>

      <Stage
        id="loading-state"
        title="Ingesting"
        description="Pixel-grid loader with shimmer and elapsed time. Drive, dots, or orbit."
      >
        <div className="flex flex-col items-center">
          <LoadingState
            key={loader}
            variant={loader}
            label="Syncing"
          />
          <VariantTabs
            value={loader}
            options={["Drive", "Dots", "Orbit"]}
            onChange={setLoader}
          />
        </div>
      </Stage>

      <Stage
        id="connector"
        title="Connector card"
        description="State, counts, last/next run, Sync now. Reconnect when refresh dies."
      >
        <MemoryConnector
          card={SLACK_CARD}
          blurb="Channels and threads — decisions that never made it into a doc."
          onSync={() => undefined}
          onDisconnect={() => undefined}
        />
      </Stage>

      <Stage
        id="sync-jobs"
        title="Sync jobs"
        description="Last run: new / distilled / error. Failed GitHub flips to completed after retry."
      >
        <div className="flex w-full max-w-lg flex-col">
          <TaskRows key={tasks} variant={tasks} />
          <VariantTabs
            value={tasks}
            options={["Capsules", "List"]}
            onChange={setTasks}
          />
        </div>
      </Stage>

      <Stage
        id="readiness"
        title="Readiness"
        description="Index progress. Product sync status lives on each connector."
      >
        <ReadinessChecklist
          steps={[
            { key: "fetched", label: "Fetched", done: true },
            { key: "distilled", label: "Distilled", done: true },
            { key: "people", label: "People resolved", done: true },
            { key: "graph", label: "Graph linked", done: false },
            { key: "indexes", label: "Indexes consistent", done: false },
          ]}
        />
      </Stage>

      <Stage
        id="insight-cards"
        title="Corpus"
        description="Ingest mix, distill spend, source share — the profile counters with a pulse."
      >
        <InsightCards />
      </Stage>

      <Stage
        id="code-block"
        title="Cited code"
        description="A GitHub chunk streaming in, copy live. Not agent-written code."
      >
        <CodeBlock />
      </Stage>
    </>
  );
}

export function DesignLanguageGallery() {
  return (
    <BuiScope className="min-h-full bg-page">
      <div className="mx-auto grid max-w-[1180px] gap-10 px-6 py-10 lg:grid-cols-[220px_1fr]">
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <p className="text-[13px] font-semibold tracking-tight text-ink">
            joel language
          </p>
          <p className="mt-1 text-[12.5px] leading-snug text-ink-2">
            Brand, atoms, then the company-brain kit. Import from{" "}
            <code className="font-mono text-[11px]">@/components/beautifului</code>.
          </p>
          <nav className="mt-5 flex flex-col gap-4">
            {NAV.map((group) => (
              <div key={group.label}>
                <p className="px-2 pb-1 text-[10.5px] font-medium tracking-[0.04em] text-ink-3 uppercase">
                  {group.label}
                </p>
                <div className="flex flex-col gap-px">
                  {group.items.map(([id, label]) => (
                    <a
                      key={id}
                      href={`#${id}`}
                      className="rounded-[8px] px-2 py-1 text-[13px] text-ink-2 hover:bg-hover hover:text-ink"
                    >
                      {label}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <div className="space-y-14">
          <BrandLanguage />
          <Atoms />
          <Components />
        </div>
      </div>
    </BuiScope>
  );
}
