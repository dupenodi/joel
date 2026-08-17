"use client";

import { cn } from "@/lib/utils";
import { useEffect } from "react";
import type { ReactNode } from "react";

export function MobileDrawer({
  open,
  onClose,
  children,
  side = "left",
  label,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  side?: "left" | "right";
  label: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <div
        className="absolute inset-0 bg-ink/30"
        aria-hidden="true"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className={cn(
          "absolute top-0 flex h-full w-[min(85vw,320px)] flex-col bg-bg shadow-[var(--shadow-md)]",
          side === "left" ? "left-0" : "right-0",
        )}
      >
        {children}
      </div>
    </div>
  );
}
