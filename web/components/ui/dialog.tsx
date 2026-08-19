"use client";

import { cn } from "@/lib/utils";
import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({
  open,
  onClose,
  title,
  children,
  locked = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  locked?: boolean;
}) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const lockedRef = useRef(locked);
  lockedRef.current = locked;

  useEffect(() => {
    if (!open) return;

    const html = document.documentElement;
    const body = document.body;
    const gap = Math.max(0, window.innerWidth - html.clientWidth);
    const prev = {
      htmlOverflow: html.style.overflow,
      bodyOverflow: body.style.overflow,
      htmlPad: html.style.paddingRight,
    };
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    if (gap > 0) html.style.paddingRight = `${gap}px`;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !lockedRef.current) onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      html.style.overflow = prev.htmlOverflow;
      body.style.overflow = prev.bodyOverflow;
      html.style.paddingRight = prev.htmlPad;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-hidden px-4 pt-[12vh] pb-4">
      <div
        className="absolute inset-0 bg-ink/25"
        aria-hidden="true"
        onClick={locked ? undefined : () => onCloseRef.current()}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative z-10 flex max-h-[min(76vh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-card bg-surface shadow-overlay",
        )}
      >
        {children}
      </div>
    </div>
  );
}
