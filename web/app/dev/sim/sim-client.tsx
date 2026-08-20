"use client";

import { ContentFrame } from "@/components/app-frame";
import { BrandMark } from "@/components/brand-mark";
import {
  BuiScope,
  LockedChat,
  PromptBar,
  StreamingText,
  ThinkingState,
  UserTurn,
} from "@/components/beautifului";
import { SourceIcon } from "@/components/source-icon";
import { useCallback, useEffect, useState } from "react";

type Example =
  | "memory"
  | "relationships"
  | "live"
  | "plan-search"
  | "absent"
  | "locked"
  | "empty";

const EXAMPLES: {
  id: Example;
  label: string;
  note: string;
  question: string;
}[] = [
  {
    id: "memory",
    label: "Memory hit",
    note: "Searching memory → answer with sources.",
    question: "Who owns billing after the Q3 reversal?",
  },
  {
    id: "relationships",
    label: "Relationships",
    note: "Walk people ↔ things, then answer.",
    question: "Who owns billing after the Q3 reversal?",
  },
  {
    id: "live",
    label: "Live check",
    note: "Hit connectors now, then answer.",
    question: "Is Maya still on-call for billing?",
  },
  {
    id: "plan-search",
    label: "Plan then search",
    note: "Actions stack — planning then searching.",
    question: "Who owns billing after the Q3 reversal?",
  },
  {
    id: "absent",
    label: "Nothing found",
    note: "Search misses → short not-in-memory answer.",
    question: "Who owns the Mars launch checklist?",
  },
];

const EXTRAS: { id: Example; label: string; note: string }[] = [
  { id: "empty", label: "Empty", note: "Welcome + composer only." },
  { id: "locked", label: "Locked", note: "Nothing indexed yet." },
];

const SLACK_ANSWER =
  "Maya Chen owns billing — the Q3 reversal flipped the edge from Priya after the June RFC. As of just now, the on-call rotation still lists Maya.";

const SLACK_SOURCES = [
  { title: "#billing-owners", provider: "slack" },
  { title: "RFC: billing ownership", provider: "github" },
  { title: "Q3 reversal note", provider: "gmail" },
];

function SlackTwin({
  phase,
  absent,
  question,
}: {
  phase: "idle" | "thinking" | "done";
  absent?: boolean;
  question: string;
}) {
  if (phase === "idle") {
    return (
      <div className="rounded-[12px] border border-dashed border-line px-3 py-4 text-[12.5px] text-ink-3">
        No bot reply in this scene.
      </div>
    );
  }

  if (phase === "thinking") {
    return (
      <div className="rounded-[12px] bg-[#1a1d21] px-3 py-4 text-[13px] text-white/50">
        joel is thinking…
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[12px] bg-[#1a1d21] text-[#d1d2d3] shadow-raised">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2.5">
        <span className="flex size-7 items-center justify-center rounded-[6px] bg-[#4A154B] text-[11px] font-bold text-white">
          j
        </span>
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-white">
            joel{" "}
            <span className="ml-1 rounded bg-white/10 px-1 text-[10px] font-medium text-white/70">
              APP
            </span>
          </p>
          <p className="truncate text-[11px] text-white/45">
            in reply to @{question.slice(0, 28)}…
          </p>
        </div>
      </div>
      <div className="space-y-3 px-3 py-3 text-[13.5px] leading-relaxed">
        <p className="whitespace-pre-wrap text-white/90">
          {absent ? "Not in the company's memory." : SLACK_ANSWER}
        </p>
        {!absent && (
          <div className="space-y-1.5 text-[12.5px] text-white/55">
            <p className="font-medium text-white/40">Sources</p>
            {SLACK_SOURCES.map((s) => (
              <div key={s.provider} className="flex items-center gap-2">
                <span className="flex size-4 items-center justify-center overflow-hidden rounded-[3px] bg-white/10">
                  <SourceIcon provider={s.provider} size={14} />
                </span>
                <span>
                  {s.title} · {s.provider}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="border-t border-white/10 pt-2 text-[11.5px] text-white/35">
          Same answer as web — plain text
          {absent ? "." : " + source links."} No thinking chrome.
        </p>
      </div>
    </div>
  );
}

/** Runs Planning, then Searching, then settles — sim-only stacking. */
function PlanThenSearch({
  runKey,
  onSettled,
}: {
  runKey: number;
  onSettled: () => void;
}) {
  const [step, setStep] = useState<"plan" | "search">("plan");

  useEffect(() => {
    setStep("plan");
  }, [runKey]);

  return (
    <div className="flex w-full flex-col gap-2">
      <ThinkingState
        key={`plan-${runKey}`}
        variant="Planning"
        onSettled={() => setStep("search")}
      />
      {step === "search" && (
        <ThinkingState
          key={`search-${runKey}`}
          variant="Searching"
          onSettled={onSettled}
        />
      )}
    </div>
  );
}

function TurnBody({
  example,
  runKey,
  onStream,
}: {
  example: Example;
  runKey: number;
  onStream: () => void;
}) {
  if (example === "plan-search") {
    return <PlanThenSearch runKey={runKey} onSettled={onStream} />;
  }

  const variant =
    example === "memory" || example === "absent"
      ? "Searching"
      : example === "relationships"
        ? "Relationships"
        : example === "live"
          ? "Live"
          : "Planning";

  return (
    <ThinkingState
      key={`${example}-${runKey}`}
      variant={variant}
      empty={example === "absent"}
      onSettled={onStream}
    />
  );
}

export function ChatSim() {
  const [example, setExample] = useState<Example>("memory");
  const [phase, setPhase] = useState<"thinking" | "streaming">("thinking");
  const [runKey, setRunKey] = useState(0);

  const meta =
    EXAMPLES.find((e) => e.id === example) ??
    EXTRAS.find((e) => e.id === example)!;
  const question =
    EXAMPLES.find((e) => e.id === example)?.question ??
    "Who owns billing after the Q3 reversal?";

  const restart = useCallback((next?: Example) => {
    if (next) setExample(next);
    setPhase("thinking");
    setRunKey((k) => k + 1);
  }, []);

  const go = (id: Example) => {
    setExample(id);
    if (id !== "locked" && id !== "empty") {
      setPhase("thinking");
      setRunKey((k) => k + 1);
    }
  };

  const isTurn =
    example !== "locked" && example !== "empty";
  const slackPhase = !isTurn
    ? "idle"
    : phase === "thinking"
      ? "thinking"
      : "done";

  return (
    <BuiScope className="min-h-full bg-page">
      <div className="mx-auto grid max-w-[1200px] gap-8 px-5 py-8 lg:grid-cols-[210px_minmax(0,1fr)_280px]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <p className="text-[13px] font-semibold tracking-tight text-ink">
            Chat sim
          </p>
          <p className="mt-1 text-[12.5px] leading-snug text-ink-2">
            Five agent turns. Actions are not exclusive — a turn can stack
            them, then stream an answer.
          </p>

          <p className="mt-5 px-2 pb-1 text-[10.5px] font-medium tracking-[0.04em] text-ink-3 uppercase">
            Examples
          </p>
          <nav className="flex flex-col gap-px">
            {EXAMPLES.map((e) => (
              <button
                key={e.id}
                type="button"
                onClick={() => go(e.id)}
                className={`rounded-[8px] px-2 py-1.5 text-left text-[13px] transition-colors ${
                  example === e.id
                    ? "bg-hover text-ink"
                    : "text-ink-2 hover:bg-hover hover:text-ink"
                }`}
              >
                {e.label}
              </button>
            ))}
          </nav>

          <p className="mt-4 px-2 pb-1 text-[10.5px] font-medium tracking-[0.04em] text-ink-3 uppercase">
            Shell
          </p>
          <nav className="flex flex-col gap-px">
            {EXTRAS.map((e) => (
              <button
                key={e.id}
                type="button"
                onClick={() => go(e.id)}
                className={`rounded-[8px] px-2 py-1.5 text-left text-[13px] transition-colors ${
                  example === e.id
                    ? "bg-hover text-ink"
                    : "text-ink-2 hover:bg-hover hover:text-ink"
                }`}
              >
                {e.label}
              </button>
            ))}
          </nav>

          {isTurn && (
            <button
              type="button"
              onClick={() => restart()}
              className="mt-4 px-2 text-[12px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
            >
              Replay turn
            </button>
          )}

          <div className="mt-5 rounded-card bg-surface p-3 shadow-hairline">
            <p className="text-[11.5px] font-medium text-ink">Agent actions</p>
            <ul className="mt-1.5 space-y-1 text-[11.5px] leading-snug text-ink-2">
              <li>
                <span className="font-medium text-ink">Planning</span> — rewrite,
                decide what to check
              </li>
              <li>
                <span className="font-medium text-ink">Searching</span> — indexed
                docs / threads
              </li>
              <li>
                <span className="font-medium text-ink">Relationships</span> —
                people ↔ things hops
              </li>
              <li>
                <span className="font-medium text-ink">Live</span> — connectors
                right now
              </li>
            </ul>
          </div>

          <a
            href="/dev/ui"
            className="mt-3 inline-block px-2 text-[12px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
          >
            ← Component gallery
          </a>
        </aside>

        <div className="flex min-h-[640px] flex-col overflow-hidden rounded-[16px] bg-canvas shadow-raised">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {example === "locked" ? (
              <div className="flex h-full min-h-[480px] items-center justify-center p-6">
                <LockedChat href="/integrations" />
              </div>
            ) : example === "empty" ? (
              <ContentFrame
                width="chat"
                className="flex h-full min-h-[480px] flex-col justify-center py-10"
              >
                <div className="mb-6 flex flex-col items-center text-center">
                  <BrandMark size={160} animated={false} />
                  <h1 className="mt-6 font-display text-[28px] leading-tight font-semibold tracking-tight text-ink">
                    Hello, Sharath.
                  </h1>
                  <p className="mt-2 text-[15px] text-ink-2">Ask about Acme.</p>
                </div>
              </ContentFrame>
            ) : (
              <ContentFrame width="chat" className="flex flex-col gap-5 py-8">
                <UserTurn>{question}</UserTurn>
                <div className="flex w-full flex-col gap-3">
                  <TurnBody
                    example={example}
                    runKey={runKey}
                    onStream={() => setPhase("streaming")}
                  />
                  {phase === "streaming" && (
                    <StreamingText
                      key={`stream-${runKey}-${example}`}
                      loop={false}
                      fill
                      absent={example === "absent"}
                    />
                  )}
                </div>
              </ContentFrame>
            )}
          </div>

          {example !== "locked" && (
            <div className="shrink-0 border-t border-line px-4 py-4">
              <ContentFrame width="chat" className="!px-0">
                <PromptBar
                  demo={false}
                  tall={example === "empty"}
                  placeholder="Ask a question…"
                  busy={isTurn && phase === "thinking"}
                  onSend={() => go("memory")}
                  onStop={() => setPhase("streaming")}
                />
              </ContentFrame>
            </div>
          )}
        </div>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
          <div>
            <p className="text-[13px] font-semibold text-ink">Slack twin</p>
            <p className="mt-1 text-[12.5px] leading-snug text-ink-2">
              {meta.note}
            </p>
          </div>
          <SlackTwin
            phase={slackPhase}
            absent={example === "absent"}
            question={question}
          />
        </aside>
      </div>
    </BuiScope>
  );
}
