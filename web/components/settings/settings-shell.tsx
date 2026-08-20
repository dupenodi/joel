"use client";

import { ContentFrame } from "@/components/app-frame";
import {
  SettingsNav,
  SettingsNavMobile,
} from "@/components/settings/settings-nav";
import { WorkspaceAvatar } from "@/components/settings/workspace-avatar";
import { getWorkspace } from "@/lib/api";
import type { Me, Workspace } from "@/lib/types";
import { useEffect, useState } from "react";

export function SettingsShell({ children }: { children: React.ReactNode }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    void getWorkspace()
      .then((data) => {
        setWorkspace(data.workspace);
        setMe(data.me);
      })
      .catch(() => {});
  }, []);

  const isAdmin =
    me?.role === "admin" || me?.role === "owner" || Boolean(me?.is_admin);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-8">
      <ContentFrame width="settings">
        <header className="mb-6">
          <p className="text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
            Settings
          </p>
          {workspace ? (
            <div className="mt-2 flex items-center gap-3">
              <WorkspaceAvatar
                name={workspace.name}
                logoUrl={workspace.logo_url}
                size={40}
              />
              <div className="min-w-0">
                <h1 className="truncate text-[18px] font-semibold tracking-tight text-ink">
                  {workspace.name}
                </h1>
                <p className="truncate text-[13px] text-ink-2">
                  {workspace.domain}
                </p>
              </div>
            </div>
          ) : (
            <h1 className="mt-1 text-[18px] font-semibold tracking-tight text-ink">
              Workspace
            </h1>
          )}
        </header>

        <div className="mb-5 md:hidden">
          <SettingsNavMobile isAdmin={isAdmin} />
        </div>

        <div className="flex gap-8">
          <aside className="hidden w-[var(--settings-nav-w)] shrink-0 md:block">
            <div className="sticky top-6">
              <SettingsNav isAdmin={isAdmin} />
            </div>
          </aside>
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </ContentFrame>
    </div>
  );
}
