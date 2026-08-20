"use client";

import { WorkspaceAvatar } from "@/components/settings/workspace-avatar";
import {
  createWorkspace,
  getAuthStatus,
  listWorkspaces,
  switchWorkspace,
} from "@/lib/api";
import { pathAfterWorkspaceSwitch, slugPreview } from "@/lib/auth";
import type { Workspace, WorkspaceMembership } from "@/lib/types";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export function WorkspaceSwitcher() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [memberships, setMemberships] = useState<WorkspaceMembership[]>([]);
  const [switching, setSwitching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void getAuthStatus()
      .then((status) => {
        if (status.state === "ok") setWorkspace(status.workspace);
      })
      .catch(() => {});
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    void listWorkspaces()
      .then((res) => setMemberships(res.workspaces))
      .catch(() => {});
  }, [open]);

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

  const label = workspace?.name ?? "Workspace";
  const currentId = workspace?.id ? Number(workspace.id) : null;
  const slug = slugPreview(name);

  function land() {
    setOpen(false);
    window.location.assign(pathAfterWorkspaceSwitch(pathname));
  }

  return (
    <div ref={rootRef} className="relative justify-self-start">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${label} workspace`}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex max-w-[16rem] items-center gap-2 rounded-control py-1 pr-1.5 pl-1 text-left transition-colors duration-150 hover:bg-hover",
          open && "bg-hover",
        )}
      >
        <WorkspaceAvatar name={label} logoUrl={workspace?.logo_url} size={28} />
        <span className="hidden min-w-0 sm:block">
          <span className="block truncate text-[13px] font-medium text-ink">
            {label}
          </span>
        </span>
        <ChevronDown />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute top-full left-0 z-40 mt-1.5 w-72 overflow-hidden rounded-card bg-surface py-1 shadow-overlay"
        >
          {memberships.length > 0 && (
            <div className="border-b border-line py-1">
              <p className="px-3 py-1.5 text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
                Workspaces
              </p>
              {memberships.map((ws) => {
                const active = currentId === ws.id;
                return (
                  <button
                    key={ws.id}
                    type="button"
                    role="menuitem"
                    disabled={switching || active}
                    onClick={() => {
                      if (active) return;
                      setSwitching(true);
                      setError(null);
                      void switchWorkspace(ws.id)
                        .then(() => land())
                        .catch((err: unknown) => {
                          setError(
                            err instanceof Error
                              ? err.message
                              : "Could not switch",
                          );
                          setSwitching(false);
                        });
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-hover disabled:opacity-70",
                      active && "bg-hover",
                    )}
                  >
                    <WorkspaceAvatar
                      name={ws.name}
                      logoUrl={ws.logo_url}
                      size={22}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-ink">
                        {ws.name}
                      </span>
                      <span className="block truncate text-[11px] text-ink-3">
                        {ws.role}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {!showCreate ? (
            <div className="py-1">
              <button
                type="button"
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-[13px] text-ink-2 hover:bg-hover hover:text-ink"
                onClick={() => setShowCreate(true)}
              >
                Create workspace…
              </button>
              <Link
                role="menuitem"
                href="/join"
                onClick={() => setOpen(false)}
                className="block px-3 py-2 text-[13px] text-ink-2 hover:bg-hover hover:text-ink"
              >
                Join workspace…
              </Link>
            </div>
          ) : (
            <form
              className="space-y-2 px-3 py-2"
              onSubmit={(e) => {
                e.preventDefault();
                setCreating(true);
                setError(null);
                void createWorkspace({
                  name: name.trim(),
                  domain: domain.trim() || undefined,
                })
                  .then(() => land())
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error ? err.message : "Could not create",
                    );
                  })
                  .finally(() => setCreating(false));
              }}
            >
              <input
                className="h-8 w-full rounded-control bg-field px-2.5 text-[13px] text-ink shadow-hairline outline-none"
                placeholder="Company name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              <input
                className="h-8 w-full rounded-control bg-field px-2.5 text-[13px] text-ink shadow-hairline outline-none"
                placeholder="Domain (optional)"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
              {slug && (
                <p className="text-[11px] text-ink-3">URL · {slug}</p>
              )}
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={creating || !name.trim()}
                  className="text-[12.5px] font-medium text-ink"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  className="text-[12.5px] text-ink-3"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
          {error && <p className="px-3 py-2 text-[12px] text-red">{error}</p>}
          <Link
            role="menuitem"
            href="/settings/general"
            onClick={() => setOpen(false)}
            className="block border-t border-line px-3 py-2 text-[13.5px] text-ink hover:bg-hover"
          >
            Workspace settings
          </Link>
        </div>
      )}
    </div>
  );
}

function ChevronDown() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0 text-ink-3"
      aria-hidden
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
