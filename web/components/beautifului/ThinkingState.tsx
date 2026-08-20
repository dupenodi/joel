"use client";

import { SourceIcon } from "@/components/source-icon";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────
 * THINKING — agent actions during a turn (not exclusive modes)
 *
 *   Planning       rewrite + decide what to check
 *   Searching      indexed docs/threads
 *   Relationships  people ↔ things graph hops
 *   Live           connector lookups right now
 *
 * Alias keys (Steps/Search/Reasoning/Lookups) still resolve.
 * The trace runs once, settles, and remains expandable.
 * ───────────────────────────────────────────────────────── */

const STAGES = [800, 600, 1800, 2600, 1600];

function useSequence(steps: number[]) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (stage >= steps.length - 1) return;
    const t = setTimeout(() => setStage((s) => s + 1), steps[stage]);
    return () => clearTimeout(t);
  }, [stage, steps]);
  return stage;
}

type StepRow = {
  kind: "step";
  primary: string;
  secondary?: string;
};

type SearchRow = {
  kind: "search";
  primary: string;
  provider: string;
  href?: string;
};

type RelRow = {
  kind: "rel";
  from: string;
  edge: string;
  to: string;
  note?: string;
  superseded?: boolean;
};

type LiveRow = {
  kind: "live";
  primary: string;
  provider: string;
  detail: string;
};

type Row = StepRow | SearchRow | RelRow | LiveRow;

type VariantDef = {
  active: string;
  done: string;
  query?: string;
  rows: Row[];
};

const VARIANTS: Record<string, VariantDef> = {
  Planning: {
    active: "Planning",
    done: "Planned",
    rows: [
      { kind: "step", primary: "Rewriting the question" },
      { kind: "step", primary: "Decide what to check", secondary: "memory · relationships" },
      { kind: "step", primary: "Reranking fused hits", secondary: "12 docs" },
    ],
  },
  Searching: {
    active: "Searching memory",
    done: "Searched memory",
    query: "who owns billing",
    rows: [
      {
        kind: "search",
        primary: "#billing-owners",
        provider: "slack",
        href: "https://slack.com/",
      },
      {
        kind: "search",
        primary: "RFC: billing ownership",
        provider: "github",
        href: "https://github.com/",
      },
      {
        kind: "search",
        primary: "Q3 reversal note",
        provider: "gmail",
        href: "https://mail.google.com/",
      },
    ],
  },
  Relationships: {
    active: "Walking relationships",
    done: "Walked relationships",
    rows: [
      {
        kind: "rel",
        from: "Maya Chen",
        edge: "OWNS",
        to: "Billing",
        note: "after Q3 reversal",
      },
      {
        kind: "rel",
        from: "Priya Shah",
        edge: "OWNED",
        to: "Billing",
        note: "12 Jun 2026",
        superseded: true,
      },
      {
        kind: "rel",
        from: "Maya Chen",
        edge: "ON_CALL",
        to: "Billing rotation",
        note: "current",
      },
    ],
  },
  Live: {
    active: "Checking live",
    done: "Checked live",
    rows: [
      {
        kind: "live",
        primary: "gmail.search",
        provider: "gmail",
        detail: "from:ops on-call billing",
      },
      {
        kind: "live",
        primary: "slack.thread",
        provider: "slack",
        detail: "#billing-owners",
      },
      {
        kind: "live",
        primary: "github.issue",
        provider: "github",
        detail: "org/billing#441",
      },
    ],
  },
};

/** Empty search for “nothing found” sim */
const SEARCHING_EMPTY: VariantDef = {
  active: "Searching memory",
  done: "Nothing in memory",
  query: "who owns the Mars launch checklist",
  rows: [],
};

const ALIAS: Record<string, string> = {
  Steps: "Planning",
  Search: "Searching",
  Reasoning: "Relationships",
  Lookups: "Live",
};

function CheckIcon({ spinning }: { spinning?: boolean }) {
  if (spinning) {
    return (
      <span
        className="size-3 shrink-0 rounded-full border-[1.5px] border-line-strong border-t-ink-2"
        style={{ animation: "spin 700ms linear infinite" }}
      />
    );
  }
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--ink-3)"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

function RelationshipHop({ row }: { row: RelRow }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-[6px] px-1.5 py-1.5 ${
        row.superseded ? "opacity-55" : ""
      }`}
    >
      <span
        className={`rounded-full bg-inset px-2 py-0.5 text-[12px] font-medium shadow-hairline ${
          row.superseded ? "text-ink-3 line-through" : "text-ink"
        }`}
      >
        {row.from}
      </span>
      <span className="font-mono text-[10.5px] tracking-[0.04em] text-ink-3">
        —[{row.edge}]→
      </span>
      <span
        className={`rounded-full bg-inset px-2 py-0.5 text-[12px] font-medium shadow-hairline ${
          row.superseded ? "text-ink-3" : "text-ink"
        }`}
      >
        {row.to}
      </span>
      {row.note && (
        <span
          className={`w-full pl-0.5 text-[11.5px] ${
            row.superseded ? "text-ink-3" : "text-ink-2"
          }`}
        >
          {row.superseded ? `Superseded · ${row.note}` : row.note}
        </span>
      )}
    </div>
  );
}

export default function ThinkingState({
  variant = "Planning",
  empty = false,
  onSettled,
}: {
  variant?: string;
  /** Searching with no hits (sim: nothing found) */
  empty?: boolean;
  onSettled?: () => void;
}) {
  const stage = useSequence(STAGES);
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(null);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);

  const resolved = ALIAS[variant] ?? variant;
  const v =
    empty && resolved === "Searching"
      ? SEARCHING_EMPTY
      : (VARIANTS[resolved] ?? VARIANTS.Planning);

  const autoExpanded = stage >= 1 && stage < 4;
  const expanded = manualExpanded ?? autoExpanded;
  const working = stage < 3;
  const visible =
    stage < 2 ? 0 : stage === 2 ? Math.min(2, Math.max(v.rows.length, 0)) : v.rows.length;
  const traceRef = useRef<HTMLDivElement>(null);
  const [lineHeight, setLineHeight] = useState(0);

  useLayoutEffect(() => {
    if (traceRef.current) setLineHeight(traceRef.current.offsetHeight);
  }, [visible, expanded, resolved, stage, empty]);

  const settledRef = useRef(false);
  useEffect(() => {
    settledRef.current = false;
  }, [resolved, empty]);

  useEffect(() => {
    if (working || settledRef.current) return;
    settledRef.current = true;
    onSettled?.();
  }, [working, onSettled]);

  return (
    <div
      key={`${resolved}-${empty}`}
      className="flex w-full max-w-95 flex-col"
      style={{
        minHeight: working || expanded ? 176 : undefined,
        transition: "min-height 400ms cubic-bezier(0.23,1,0.32,1)",
      }}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setManualExpanded((current) => !(current ?? autoExpanded))}
        className="-mx-1.5 flex w-fit items-center gap-2 rounded-control px-1.5 py-1
          transition-colors duration-100 hover:bg-hover-2"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill={working ? "var(--ink-2)" : "var(--ink-3)"}
        >
          <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
        </svg>
        <span role="status" className="contents">
          {working ? (
            <span
              className="bg-clip-text text-[13px] font-medium whitespace-nowrap text-transparent"
              style={{
                backgroundImage:
                  "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
                backgroundSize: "200% 100%",
                animation: "shimmer-text 1.4s linear infinite",
              }}
            >
              {v.active}
            </span>
          ) : (
            <span
              className="text-[13px] font-medium whitespace-nowrap text-ink-2"
              style={{ animation: "fade-in 350ms ease-out both" }}
            >
              {v.done}
            </span>
          )}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="transition-transform duration-300"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)" }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-400"
        style={{
          gridTemplateRows: expanded ? "1fr" : "0fr",
          opacity: expanded ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <div className="relative mt-1 ml-[5px] pl-4">
            <span
              aria-hidden
              className="absolute left-[3px] w-px bg-line"
              style={{
                top: -8,
                height: lineHeight ? lineHeight - 2 : 0,
                transition: "height 500ms cubic-bezier(0.23,1,0.32,1)",
              }}
            />
            <div ref={traceRef} className="flex flex-col gap-1 py-1">
              {v.query && (
                <div
                  className="flex h-6 items-center gap-2 px-1.5"
                  style={{
                    animation: expanded
                      ? "fade-up 300ms cubic-bezier(0.23,1,0.32,1) both"
                      : undefined,
                  }}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="var(--ink-3)"
                    strokeWidth="2"
                    strokeLinecap="round"
                    className="shrink-0"
                  >
                    <circle cx="11" cy="11" r="7" />
                    <path d="M21 21l-4.3-4.3" />
                  </svg>
                  <span className="text-[12.5px] text-ink-2">{v.query}</span>
                </div>
              )}

              {v.rows.slice(0, visible).map((row, i) => {
                const animation = {
                  animation: `fade-up 320ms cubic-bezier(0.23,1,0.32,1) ${i * 120}ms both`,
                };
                const rowClass =
                  "flex min-h-7 w-full items-center gap-2 rounded-[6px] px-1.5 py-0.5 text-left";

                if (row.kind === "rel") {
                  return (
                    <div key={`${row.from}-${row.edge}-${row.to}`} style={animation}>
                      <RelationshipHop row={row} />
                    </div>
                  );
                }

                if (row.kind === "search") {
                  return (
                    <a
                      key={row.primary}
                      href={row.href}
                      target="_blank"
                      rel="noreferrer"
                      className={`${rowClass} transition-colors duration-150 hover:bg-hover`}
                      style={animation}
                    >
                      <SourceIcon provider={row.provider} size={14} className="rounded-[3px]" />
                      <span className="min-w-0 truncate text-[12.5px] font-medium text-ink animated-underline">
                        {row.primary}
                      </span>
                      <span className="shrink-0 font-mono text-[11.5px] text-ink-3">
                        {row.provider}
                      </span>
                    </a>
                  );
                }

                if (row.kind === "live") {
                  const selected = selectedTool === row.primary;
                  return (
                    <button
                      key={row.primary}
                      type="button"
                      aria-pressed={selected}
                      onClick={() =>
                        setSelectedTool(selected ? null : row.primary)
                      }
                      className={`${rowClass} transition-colors duration-150 ${
                        selected ? "bg-inset" : "hover:bg-hover"
                      }`}
                      style={animation}
                    >
                      <SourceIcon provider={row.provider} size={14} className="rounded-[3px]" />
                      <span className="min-w-0 truncate font-mono text-[12.5px] font-medium text-ink">
                        {row.primary}
                      </span>
                      <span className="shrink-0 truncate font-mono text-[11.5px] text-ink-3">
                        {row.detail}
                      </span>
                    </button>
                  );
                }

                return (
                  <div key={row.primary} className={rowClass} style={animation}>
                    <CheckIcon
                      spinning={
                        i === visible - 1 && working && resolved === "Planning"
                      }
                    />
                    <span className="min-w-0 truncate text-[12.5px] font-medium text-ink">
                      {row.primary}
                    </span>
                    {row.secondary && (
                      <span className="shrink-0 text-[11.5px] text-ink-3">
                        {row.secondary}
                      </span>
                    )}
                  </div>
                );
              })}

              {resolved === "Searching" && stage >= 3 && v.rows.length > 0 && (
                <span
                  className="text-[12px] text-ink-3"
                  style={{ animation: "fade-in 300ms ease-out both" }}
                >
                  +7 more
                </span>
              )}

              {resolved === "Searching" &&
                empty &&
                stage >= 2 &&
                v.rows.length === 0 && (
                  <p
                    className="px-1.5 py-1 text-[12.5px] text-ink-3"
                    style={{ animation: "fade-in 300ms ease-out both" }}
                  >
                    No matching docs in memory.
                  </p>
                )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
