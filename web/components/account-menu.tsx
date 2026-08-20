"use client";

import { PersonAvatar } from "@/components/settings/workspace-avatar";
import { getAuthStatus, logout } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export function AccountMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void getAuthStatus()
      .then((status) => {
        if (status.state === "ok") setMe(status.me);
      })
      .catch(() => {});
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = me?.display_name ?? "You";
  const settingsActive = pathname.startsWith("/settings");

  return (
    <div ref={rootRef} className="relative justify-self-end">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${label} account`}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex max-w-[12rem] items-center gap-2 rounded-control py-1 pr-1.5 pl-1 text-left transition-colors duration-150 hover:bg-hover",
          (open || settingsActive) && "bg-hover",
        )}
      >
        <PersonAvatar name={label} size={28} />
        <span className="hidden min-w-0 sm:block">
          <span className="block truncate text-[13px] font-medium text-ink">
            {label}
          </span>
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute top-full right-0 z-40 mt-1.5 w-52 overflow-hidden rounded-card bg-surface py-1 shadow-overlay"
        >
          {me && (
            <p className="truncate px-3 py-2 text-[12px] text-ink-3">
              {me.email}
            </p>
          )}
          <Link
            role="menuitem"
            href="/settings/profile"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-[13.5px] text-ink hover:bg-hover"
          >
            Profile
          </Link>
          <Link
            role="menuitem"
            href="/settings/general"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-[13.5px] text-ink hover:bg-hover"
          >
            Settings
          </Link>
          <button
            type="button"
            role="menuitem"
            className="block w-full px-3 py-2 text-left text-[13.5px] text-ink hover:bg-hover"
            onClick={() => {
              setOpen(false);
              void logout().then(() => router.replace("/login"));
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
