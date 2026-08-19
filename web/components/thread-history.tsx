"use client";

import GlideMenu from "@/components/beautifului/primitives/glide-menu";
import type { Conversation } from "@/lib/types";
import { cn, formatRelative } from "@/lib/utils";
import { useEffect, useRef, useState } from "react";

function HistoryIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

export function ThreadHistory({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointer(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (conversations.length === 0) return null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="Recent activity"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-[14px] text-ink-2 transition-[background-color,color,transform] duration-150 hover:bg-hover hover:text-ink active:scale-[0.96]",
          open && "bg-hover text-ink",
        )}
      >
        <HistoryIcon />
      </button>
      {open && (
        <div
          className="absolute left-0 bottom-full z-50 mb-2 w-72 overflow-hidden rounded-card bg-surface shadow-overlay"
          style={{
            animation: "pop-in 180ms cubic-bezier(0.23,1,0.32,1) both",
            transformOrigin: "bottom left",
          }}
        >
          <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
            <p className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
              Recent
            </p>
            {activeId && (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onNew();
                }}
                className="text-[12px] font-medium text-accent-ink hover:underline"
              >
                New chat
              </button>
            )}
          </div>
          <GlideMenu
            className="max-h-72 overflow-y-auto p-1"
            highlightClassName="inset-x-1 rounded-[6px] bg-hover"
          >
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <button
                  key={c.id}
                  type="button"
                  data-menu-row
                  aria-current={active ? "true" : undefined}
                  onClick={() => {
                    setOpen(false);
                    onSelect(c.id);
                  }}
                  className={cn(
                    "relative z-10 flex w-full items-baseline justify-between gap-3 rounded-[6px] px-2.5 py-2 text-left",
                    active ? "text-ink" : "text-ink-2",
                  )}
                >
                  <span className="min-w-0 truncate text-[14px] font-medium">
                    {c.title}
                  </span>
                  <span className="shrink-0 text-[11.5px] text-ink-3">
                    {formatRelative(c.created_at)}
                  </span>
                </button>
              );
            })}
          </GlideMenu>
        </div>
      )}
    </div>
  );
}
