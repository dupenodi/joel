"use client";

import {
  CheckIcon,
  ClipboardIcon,
} from "@/components/beautifului/primitives/copy-button";
import { useCallback, useEffect, useState } from "react";

/* ─────────────────────────────────────────────────────────
 * CODE BLOCK
 * Agent-written code streams line by line; copy is live.
 * ───────────────────────────────────────────────────────── */

const LINE_MS = 240;
const HOLD_MS = 3200;

type Tok = { t: string; c?: "kw" | "str" | "num" | "fn" | "dim" };

const LINES: Tok[][] = [
  [{ t: "export async function ", c: "kw" }, { t: "ownsBilling", c: "fn" }, { t: "() {", c: "dim" }],
  [{ t: "  const ", c: "kw" }, { t: "edge = " }, { t: "await ", c: "kw" }, { t: "graph." }, { t: "path", c: "fn" }, { t: "(", c: "dim" }, { t: "\"Maya\"", c: "str" }, { t: ", ", c: "dim" }, { t: "\"Billing\"", c: "str" }, { t: ");", c: "dim" }],
  [{ t: "  if ", c: "kw" }, { t: "(!edge.current) " }, { t: "throw ", c: "kw" }, { t: "new ", c: "kw" }, { t: "StaleEdge", c: "fn" }, { t: "();", c: "dim" }],
  [{ t: "  return ", c: "kw" }, { t: "edge.owner;" }],
  [{ t: "}", c: "dim" }],
];

const COLORS: Record<string, string> = {
  kw: "var(--accent-ink)",
  str: "var(--green)",
  num: "var(--orange)",
  fn: "var(--ink)",
  dim: "var(--ink-3)",
};

const RAW = `export async function ownsBilling() {
  const edge = await graph.path("Maya", "Billing");
  if (!edge.current) throw new StaleEdge();
  return edge.owner;
}`;

export default function CodeBlock() {
  const [count, setCount] = useState(0);
  const [copied, setCopied] = useState(false);
  const done = count >= LINES.length;

  /* stream in once, then hold — replaying reads as noise */
  useEffect(() => {
    if (done) return;
    const t = setTimeout(() => setCount((c) => c + 1), count === 0 ? 400 : LINE_MS);
    return () => clearTimeout(t);
  }, [count, done]);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(RAW).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, []);

  return (
    <div className="w-full max-w-95 overflow-hidden rounded-card bg-surface shadow-hairline">
      {/* header */}
      <div className="primitive-card-bar flex items-center justify-between border-b border-line">
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-[12px] font-medium text-ink">billing.ts</span>
          <span className="text-[11.5px] text-ink-3">TypeScript</span>
        </span>
        <button
          aria-label="Copy code"
          onClick={copy}
          className={`flex h-6 items-center gap-1 rounded-[6px] px-1.5 text-[11.5px]
            font-medium transition-colors duration-100 hover:bg-hover
            ${copied ? "text-green" : "text-ink-3 hover:text-ink"}`}
        >
          {copied ? <CheckIcon size={10} /> : <ClipboardIcon size={10} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {/* code */}
      <pre className="min-h-[137px] bg-inset px-3 py-2.5 font-mono text-[11.5px] leading-[1.7]">
        {LINES.slice(0, count).map((line, i) => (
          <div
            key={i}
            className="flex"
            style={{ animation: "fade-up 250ms cubic-bezier(0.23,1,0.32,1) both" }}
          >
            <span className="w-5 shrink-0 text-right text-[10.5px] leading-[1.86] text-ink-3/60 select-none">
              {i + 1}
            </span>
            <span className="pl-2.5 whitespace-pre">
              {line.map((tok, j) => (
                <span key={j} style={{ color: tok.c ? COLORS[tok.c] : "var(--ink-2)" }}>
                  {tok.t}
                </span>
              ))}
              {i === count - 1 && !done && (
                <span className="ml-0.5 inline-block h-3 w-[3px] translate-y-0.5 rounded-full bg-accent" />
              )}
            </span>
          </div>
        ))}
              </pre>
    </div>
  );
}
