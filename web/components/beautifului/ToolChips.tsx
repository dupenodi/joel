"use client";

import { useEffect, useState } from "react";

/* ─────────────────────────────────────────────────────────
 * TOOL CHIPS
 * Planner + retrieval lanes + a live lookup, then citation chips.
 * ───────────────────────────────────────────────────────── */

const STEP_MS = 700;

const Icons: Record<string, React.ReactNode> = {
  think: <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />,
  write: <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" /></g>,
  run: <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 17l6-5-6-5M12 19h8" /></g>,
  read: <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></g>,
};

type DetailLine = { text: string; tone?: "add" };

const ROWS: { icon: string; label: string; chip: string; mono: boolean; detailMono: boolean; detail: DetailLine[] }[] = [
  {
    icon: "think", label: "Plan", chip: "Who owns billing after Q3?", mono: false, detailMono: false,
    detail: [
      { text: "Need the current OWNS edge, not the June one." },
      { text: "Run graph + phrase; live Gmail if memory is thin." },
    ],
  },
  {
    icon: "read", label: "VECTOR", chip: "12 docs · RRF", mono: true, detailMono: false,
    detail: [
      { text: "RFC: billing ownership" },
      { text: "#billing-owners thread from Tuesday" },
    ],
  },
  {
    icon: "run", label: "GRAPH", chip: "Maya -[:OWNS]-> Billing", mono: true, detailMono: true,
    detail: [
      { text: "Priya -[:OWNED]-> Billing  dated 2026-06-12" },
      { text: "Maya -[:OWNS]-> Billing   dated 2026-09-03" },
    ],
  },
  {
    icon: "write", label: "LIVE", chip: "gmail.search", mono: true, detailMono: false,
    detail: [
      { text: "As of just now: on-call still lists Maya Chen." },
      { text: "Thread: “billing owner rotation” · 14m ago" },
    ],
  },
];

const CITATIONS = [
  { title: "#billing-owners", source: "slack" },
  { title: "RFC: billing ownership", source: "github" },
  { title: "Q3 reversal note", source: "gmail" },
];

export default function ToolChips() {
  const [step, setStep] = useState(0);
  const [open, setOpen] = useState(true);
  const [openRows, setOpenRows] = useState<Set<string>>(new Set());
  const total = ROWS.length + 1;

  useEffect(() => {
    if (step >= total) return;
    const t = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [step, total]);

  const toggleRow = (label: string) =>
    setOpenRows((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  return (
    <div className="min-h-[220px] w-full max-w-80 pb-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="-mx-1.5 flex w-fit items-center gap-1.5 rounded-control px-1.5 py-1 text-[12.5px] text-ink-2 transition-colors duration-100 hover:bg-hover-2"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform duration-200" style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
        <span className="tabular-nums">3 lanes, 1 live lookup</span>
      </button>

      <div className="grid transition-[grid-template-rows,opacity] duration-300" style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}>
        <div className="-mx-1 overflow-hidden px-1.5 pb-1">
        <div className="mt-1.5 flex flex-col gap-1">
          {ROWS.slice(0, step).map((row) => {
            const rowOpen = openRows.has(row.label);
            return (
            <div key={row.label} style={{ animation: "fade-up 300ms cubic-bezier(0.23,1,0.32,1) both" }}>
              <button
                type="button"
                aria-expanded={rowOpen}
                onClick={() => toggleRow(row.label)}
                className="group/row -mx-[3px] flex h-7 w-[calc(100%+6px)] min-w-0 items-center gap-2 rounded-control px-[3px] text-left transition-colors duration-100 hover:bg-hover-2"
              >
                <span className="relative flex size-4 shrink-0 items-center justify-center text-ink-3">
                  <svg
                    width="13" height="13" viewBox="0 0 24 24" fill={row.icon === "think" ? "currentColor" : "none"} stroke="currentColor"
                    className={`transition-opacity duration-100 group-hover/row:opacity-0 ${rowOpen ? "opacity-0" : ""}`}
                  >
                    {Icons[row.icon]}
                  </svg>
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
                    className={`absolute transition-[opacity,transform] duration-150 group-hover/row:opacity-100 ${rowOpen ? "opacity-100" : "opacity-0"}`}
                    style={{ transform: rowOpen ? "rotate(0deg)" : "rotate(-90deg)" }}
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </span>
                <span className="shrink-0 text-[12.5px] font-medium text-ink">{row.label}</span>
                <span
                  className={`inline-flex h-5.5 min-w-0 flex-1 cursor-pointer items-center truncate rounded-chip bg-field px-1.5
                    text-[11.5px] text-ink-2 shadow-hairline transition-colors duration-100 hover:bg-hover-2
                    ${row.mono ? "font-mono" : ""}`}
                >
                  {row.chip}
                </span>
              </button>

              <div
                className="grid transition-[grid-template-rows,opacity] duration-300"
                style={{ gridTemplateRows: rowOpen ? "1fr" : "0fr", opacity: rowOpen ? 1 : 0, transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)" }}
              >
                <div className="min-h-0 overflow-hidden">
                  <div className="mt-0.5 mb-1 ml-2 flex flex-col gap-0.5 border-l border-line py-0.5 pl-3.5">
                    {row.detail.map((line) => (
                      <span
                        key={line.text}
                        className={`truncate text-[11.5px] leading-[1.6] ${row.detailMono ? "font-mono" : ""} ${line.tone === "add" ? "text-green" : "text-ink-2"}`}
                      >
                        {line.text}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            );
          })}
        </div>

      {step >= total && (
        <div className="mt-2.5 flex max-w-full flex-wrap gap-1.5 border-t border-line pt-2.5">
          {CITATIONS.map((c, i) => (
            <span
              key={c.title}
              className="inline-flex h-7 max-w-full items-center gap-1.5 rounded-chip bg-surface px-2 text-[11.5px] text-ink shadow-btn"
              style={{ animation: `pop-in 250ms cubic-bezier(0.23,1,0.32,1) ${i * 80}ms both` }}
            >
              <span className="min-w-0 truncate">{c.title}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-ink-3">{c.source}</span>
            </span>
          ))}
        </div>
      )}
        </div>
      </div>
    </div>
  );
}

