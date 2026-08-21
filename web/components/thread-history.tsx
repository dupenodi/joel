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

function PlusIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
    </svg>
  );
}

const chromeBtn =
  "flex size-9 shrink-0 items-center justify-center rounded-[14px] text-ink-2 transition-[background-color,color,transform] duration-150 hover:bg-hover hover:text-ink active:scale-[0.96]";

export function NewChatButton({
  onClick,
  pressed = false,
}: {
  onClick: () => void;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label="New chat"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(chromeBtn, pressed && "bg-hover text-ink")}
    >
      <PlusIcon />
    </button>
  );
}

export function ThreadHistory({
  conversations,
  activeId,
  onSelect,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const activeRowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setConfirming(null);
      return;
    }
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
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
        aria-label={
          activeId
            ? `Recent chats, current: ${conversations.find((c) => c.id === activeId)?.title ?? "chat"}`
            : "Recent chats"
        }
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((v) => !v)}
        className={cn(chromeBtn, (open || activeId) && "bg-hover text-ink")}
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
          </div>
          <GlideMenu
            className="max-h-72 overflow-y-auto p-1"
            role="listbox"
            aria-label="Recent chats"
            highlightClassName="inset-x-1 rounded-[6px] bg-hover"
          >
            {conversations.map((c) => {
              const active = c.id === activeId;
              const pending = confirming === c.id;
              return (
                <div
                  key={c.id}
                  ref={active ? activeRowRef : undefined}
                  data-menu-row
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "group relative z-10 flex w-full items-center gap-1 rounded-[6px] px-1 py-0.5",
                    active ? "bg-hover text-ink" : "text-ink-2",
                  )}
                >
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      setOpen(false);
                      onSelect(c.id);
                    }}
                    className="min-w-0 flex-1 px-1.5 py-1.5 text-left"
                  >
                    <span className="block truncate text-[14px] font-medium">
                      {c.title}
                    </span>
                    <span className="block text-[11.5px] text-ink-3">
                      {formatRelative(c.updated_at ?? c.created_at)}
                    </span>
                  </button>
                  {pending ? (
                    <button
                      type="button"
                      onClick={() => {
                        setConfirming(null);
                        onDelete(c.id);
                      }}
                      className="shrink-0 rounded-[6px] px-2 py-1 text-[12px] font-medium text-red hover:bg-red-tint"
                    >
                      Delete
                    </button>
                  ) : (
                    <button
                      type="button"
                      aria-label={`Delete ${c.title}`}
                      onClick={() => setConfirming(c.id)}
                      className="flex size-7 shrink-0 items-center justify-center rounded-[6px] text-ink-3 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-hover hover:text-ink focus-visible:opacity-100"
                    >
                      <TrashIcon />
                    </button>
                  )}
                </div>
              );
            })}
          </GlideMenu>
        </div>
      )}
    </div>
  );
}
