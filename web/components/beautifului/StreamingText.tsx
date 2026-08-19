"use client";

import { useEffect, useState } from "react";

/* ─────────────────────────────────────────────────────────
 * STREAMING TEXT
 * Words resolve out of blur, inline citations appear in
 * context, then actions and follow-up prompts become usable.
 * ───────────────────────────────────────────────────────── */

const WORD_MS = 55;
const HOLD_MS = 3400;

type Token = { text: string; cite?: boolean };

const TOKENS: Token[] = [
  ..."Maya Chen owns billing — the Q3 reversal flipped the edge from Priya after the June RFC."
    .split(" ")
    .map((text) => ({ text })),
  { text: "", cite: true },
  ..."As of just now, the on-call rotation still lists Maya."
    .split(" ")
    .map((text) => ({ text })),
];

const FOLLOW_UPS = [
  "What did Priya own before the reversal",
  "Who else is on the billing on-call",
];

const SOURCE_IMAGES = {
  slack:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%234A154B'/%3E%3Ccircle cx='22' cy='32' r='7' fill='%23E01E5A'/%3E%3Ccircle cx='42' cy='32' r='7' fill='%2336C5F0'/%3E%3Ccircle cx='32' cy='22' r='7' fill='%232EB67D'/%3E%3Ccircle cx='32' cy='42' r='7' fill='%23ECB22E'/%3E%3C/svg%3E",
  github:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23181818'/%3E%3Cpath d='M32 14c-10 0-18 8.1-18 18.1 0 8 5.2 14.8 12.4 17.2.9.2 1.2-.4 1.2-.9v-3.2c-5 .1-6.1-2.4-6.1-2.4-.8-2.1-2-2.6-2-2.6-1.7-1.1.1-1.1.1-1.1 1.8.1 2.8 1.9 2.8 1.9 1.6 2.8 4.3 2 5.3 1.5.2-1.2.6-2 1.1-2.5-4-.5-8.2-2-8.2-9 0-2 0.7-3.6 1.9-4.9-.2-.5-.8-2.3.2-4.8 0 0 1.5-.5 5 1.9a17 17 0 0 1 9.1 0c3.5-2.4 5-1.9 5-1.9 1 2.5.4 4.3.2 4.8 1.2 1.3 1.9 2.9 1.9 4.9 0 7-4.2 8.5-8.2 9 .7.6 1.2 1.7 1.2 3.4v5.1c0 .5.3 1.1 1.2.9C44.8 46.9 50 40.1 50 32.1 50 22.1 42 14 32 14z' fill='%23fff'/%3E%3C/svg%3E",
  gmail:
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23EA4335'/%3E%3Cpath d='M14 20h36v24H14z' fill='%23fff'/%3E%3Cpath d='M14 20l18 13 18-13' fill='none' stroke='%23EA4335' stroke-width='4'/%3E%3C/svg%3E",
};

const SOURCES = [
  { name: "#billing-owners", domain: "slack", href: "https://slack.com/", image: SOURCE_IMAGES.slack },
  { name: "RFC: billing ownership", domain: "github", href: "https://github.com/", image: SOURCE_IMAGES.github },
  { name: "Q3 reversal note", domain: "gmail", href: "https://mail.google.com/", image: SOURCE_IMAGES.gmail },
];

function sourceImage(source: (typeof SOURCES)[number]) {
  return source.image;
}

function SourceChip() {
  const source = SOURCES[0];
  return (
    <a
      href={source.href}
      target="_blank"
      rel="noreferrer"
      className="ml-0 mr-1 inline-flex h-4.5 translate-y-[-1px] items-center gap-1 rounded-[5px]
        bg-inset pr-[3px] pl-[3px] align-middle font-mono text-[10.5px] text-ink-2 shadow-hairline
        transition-colors duration-150 hover:bg-hover hover:text-ink"
      style={{ animation: "pop-in 250ms cubic-bezier(0.23,1,0.32,1) both" }}
    >
      <img src={sourceImage(source)} alt="" className="source-avatar size-3 rounded-[3px]" />
      <span>{source.domain}</span>
    </a>
  );
}

const ACTION_ICONS: React.ReactNode[] = [
  <g key="copy"><rect x="9" y="9" width="12" height="12" rx="2.5" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></g>,
  <path key="retry" d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6" />,
  <path key="up" d="M7 10v12M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88z" />,
  <path key="down" d="M17 14V2M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88z" />,
];

export default function StreamingText({
  loop = true,
  fill = false,
  onDone,
}: {
  variant?: string;
  /** restart the stream after a hold; turn off when embedding in a real thread */
  loop?: boolean;
  /** fill the parent width instead of the gallery's fixed measure */
  fill?: boolean;
  onDone?: () => void;
}) {
  const [count, setCount] = useState(0);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const done = count >= TOKENS.length;

  useEffect(() => {
    if (done && !loop) {
      onDone?.();
      return;
    }
    const t = setTimeout(
      () => setCount((c) => (c >= TOKENS.length ? 0 : c + 1)),
      done ? HOLD_MS : WORD_MS,
    );
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count, done, loop]);

  return (
    <div className={fill ? "w-full" : "min-h-[15.5rem] w-full max-w-95"}>
      <p className="text-[13px] leading-relaxed text-ink">
        {TOKENS.slice(0, count).map((token, i) =>
          token.cite ? (
            <SourceChip key={i} />
          ) : (
            <span
              key={i}
              className="inline [will-change:filter,opacity]"
              style={{ animation: "stream-in 420ms cubic-bezier(0.22,0.61,0.25,1) both" }}
            >
              {token.text}{" "}
            </span>
          ),
        )}
        {!done && (
          <span
            className="ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 rounded-full bg-ink"
            style={{ animation: "fade-in 150ms ease-out both" }}
          />
        )}
      </p>

      {/* action icons row */}
      <div
        className="mt-2 flex items-center gap-0.5 transition-opacity duration-400"
        style={{ opacity: done ? 1 : 0, pointerEvents: done ? "auto" : "none" }}
      >
        {ACTION_ICONS.map((icon, i) => (
          <button
            key={i}
            type="button"
            aria-label="Action"
            className="flex size-6 items-center justify-center rounded-[6px] text-ink-3
              transition-colors duration-100 hover:bg-hover-2 hover:text-ink-2"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              {icon}
            </svg>
          </button>
        ))}
        <button
          type="button"
          aria-expanded={sourcesOpen}
          onClick={() => setSourcesOpen((current) => !current)}
          className="ml-1.5 flex items-center gap-1.5 rounded-[6px] px-1 py-0.5 text-left transition-colors duration-150 hover:bg-hover"
        >
          <span className="flex -space-x-1">
            {SOURCES.map((source) => (
              <img
                key={source.domain}
                src={sourceImage(source)}
                alt=""
                className="source-avatar size-3.5 rounded-full bg-surface shadow-[0_0_0_1.5px_var(--canvas)]"
              />
            ))}
          </span>
          <span className="text-[12px] text-ink-2">3 sources</span>
        </button>
      </div>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-300"
        style={{
          gridTemplateRows: done && sourcesOpen ? "1fr" : "0fr",
          opacity: done && sourcesOpen ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <div className="mt-1.5 flex flex-col rounded-[10px] bg-inset p-1 shadow-hairline">
            {SOURCES.map((source) => (
              <a
                key={source.domain}
                href={source.href}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 rounded-[6px] px-1.5 py-1 text-[12px] text-ink-2 transition-colors duration-150 hover:bg-hover hover:text-ink"
              >
                <img src={sourceImage(source)} alt="" className="source-avatar size-4 rounded-[4px]" />
                <span className="animated-underline">{source.name}</span>
                <span className="ml-auto font-mono text-[10.5px] text-ink-3">{source.domain}</span>
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* follow-ups */}
      <div
        className="mt-2.5 transition-opacity duration-400"
        style={{ opacity: done ? 1 : 0, pointerEvents: done ? "auto" : "none" }}
      >
        <p className="text-[12px] font-medium text-ink-2">Follow-ups</p>
        <div className="mt-0.5 flex flex-col">
          {FOLLOW_UPS.map((text, i) => (
            <button
              key={text}
              className="-mx-1.5 flex items-center gap-2 rounded-[7px] border-b border-line
                px-1.5 py-1.5 text-left text-[12.5px] text-ink transition-colors
                duration-100 hover:bg-hover-2"
              style={
                done
                  ? { animation: `fade-up 350ms cubic-bezier(0.23,1,0.32,1) ${i * 90}ms both` }
                  : { opacity: 0 }
              }
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
                <path d="M9 10l-5 5 5 5" />
                <path d="M20 4v7a4 4 0 0 1-4 4H4" />
              </svg>
              {text}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
