"use client";

import { Switch } from "@/components/beautifului/primitives/switch";
import { PauseToggleSkeleton } from "@/components/skeletons";
import { getSettings, getWorkspace, putSettings } from "@/lib/api";
import { useEffect, useState } from "react";

export function PauseToggle() {
  const [enabled, setEnabled] = useState(true);
  const [admin, setAdmin] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void Promise.all([getSettings(), getWorkspace()])
      .then(([s, ws]) => {
        setEnabled(s.sync_enabled);
        setAdmin(ws.me.role === "admin" || ws.me.role === "owner" || Boolean(ws.me.is_admin));
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  if (!ready) return <PauseToggleSkeleton />;
  if (!admin) {
    return (
      <span className="text-[13px] font-medium text-ink-3">
        {enabled ? "Sync on" : "Paused"}
      </span>
    );
  }

  return (
    <Switch
      checked={enabled}
      label={enabled ? "Sync on" : "Paused"}
      onCheckedChange={(on) => {
        setEnabled(on);
        void putSettings({ sync_enabled: on ? "true" : "false" }).catch(() =>
          setEnabled(!on),
        );
      }}
    />
  );
}
