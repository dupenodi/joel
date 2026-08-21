"use client";

import { useLayoutEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────
 * PROMPT BAR — simple question → send
 * Textarea + send (or stop while busy). No distill, slash
 * commands, @ sources, model picker, or dictation.
 * ───────────────────────────────────────────────────────── */

function Icon({
  children,
  size = 15,
  strokeWidth = 1.8,
}: {
  children: React.ReactNode;
  size?: number;
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export default function PromptBar({
  variant = "Rounded",
  demo: _demo = false,
  tall = false,
  placeholder,
  disabled = false,
  busy = false,
  autoFocus = false,
  onSend,
  onStop,
}: {
  variant?: string;
  /** kept for gallery/call-site compat; ignored */
  demo?: boolean;
  /** hero sizing: taller empty-state input */
  tall?: boolean;
  placeholder?: string;
  disabled?: boolean;
  busy?: boolean;
  autoFocus?: boolean;
  onSend?: (text: string) => void;
  onStop?: () => void;
}) {
  const pill = variant === "Pill";
  const [draft, setDraft] = useState("");
  const [expanded, setExpanded] = useState(false);
  const wide = expanded || tall;
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const measureRef = useRef<HTMLSpanElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const input = inputRef.current;
    const measure = measureRef.current;
    const row = rowRef.current;
    if (!input || !measure || !row) return;

    const sendWidth = 28;
    const gap = 4;
    const inlineInputWidth = row.clientWidth - sendWidth - gap;
    const needsFullWidth =
      draft.includes("\n") || measure.offsetWidth + 8 > inlineInputWidth;
    if (needsFullWidth !== expanded) setExpanded(needsFullWidth);

    const minHeight = 32;
    const maxHeight = 100;
    input.style.height = "0px";
    const contentHeight = input.scrollHeight;
    input.style.height = `${Math.min(Math.max(contentHeight, minHeight), maxHeight)}px`;
    input.style.overflowY = contentHeight > maxHeight ? "auto" : "hidden";
  }, [draft, expanded, tall]);

  const canSend = !disabled && !busy && draft.trim().length > 0;
  const send = () => {
    if (!canSend) return;
    onSend?.(draft.trim());
    setDraft("");
  };

  return (
    <div data-promptbar className="w-full">
      <div
        className={`relative isolate flex flex-col gap-1.5 overflow-hidden border border-line bg-surface p-1.5 shadow-card transition-[border-color,border-radius] duration-150 focus-within:border-line-strong ${
          pill ? (wide ? "rounded-[24px]" : "rounded-full") : "rounded-[14px]"
        }`}
      >
        <span
          ref={measureRef}
          aria-hidden="true"
          className="pointer-events-none absolute invisible whitespace-pre text-[14px] leading-[20px]"
        >
          {draft}
        </span>

        <div
          ref={rowRef}
          className={`grid items-end gap-1 ${
            wide
              ? "grid-cols-[minmax(0,1fr)_28px]"
              : "grid-cols-[minmax(0,1fr)_28px]"
          }`}
        >
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            autoFocus={autoFocus}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                send();
              }
            }}
            disabled={disabled}
            placeholder={placeholder ?? "Ask a question…"}
            aria-label="Ask a question"
            className={`${tall ? "min-h-[80px]" : "min-h-8"} min-w-0 w-full resize-none bg-transparent px-2 py-[5px] text-[14px] leading-[20px] text-ink outline-none [overflow-wrap:anywhere] placeholder:text-ink-3 ${
              wide ? "col-span-full col-start-1 row-start-1" : "col-start-1 row-start-1"
            }`}
          />

          <button
            type="button"
            aria-label={busy ? "Stop" : "Send"}
            disabled={busy ? false : !canSend}
            onClick={busy ? onStop : send}
            className={`flex size-7 shrink-0 items-center justify-center transition-[background-color,color,transform] duration-200 enabled:active:scale-[0.94] ${
              pill ? "rounded-full" : "rounded-[8px]"
            } ${wide ? "col-start-2 row-start-2 justify-self-end" : "col-start-2 row-start-1"}`}
            style={{
              background: busy || canSend ? "var(--ink)" : "var(--line-strong)",
              color: busy || canSend ? "var(--surface)" : "var(--ink-2)",
            }}
          >
            {busy ? (
              <Icon size={12} strokeWidth={2.6}>
                <rect x="6" y="6" width="12" height="12" rx="1.5" />
              </Icon>
            ) : (
              <Icon size={16} strokeWidth={2.4}>
                <path d="M12 19V5M5 12l7-7 7 7" />
              </Icon>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
