"use client";

import { SettingsEmpty, SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Stat } from "@/components/stat";
import { getProfile } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { useEffect, useState } from "react";

export function UsagePanel() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return <SettingsSkeleton />;

  const spend = profile?.spend_30d ?? {};
  const spendTotal = Object.values(spend).reduce((a, n) => a + n, 0);

  return (
    <SettingsSection
      title="Usage"
      description="LLM calls over the last 30 days, by pipeline stage."
    >
      {spendTotal === 0 ? (
        <SettingsEmpty>
          No LLM calls yet. Ask something in Chat or sync a connector to see
          spend here.
        </SettingsEmpty>
      ) : (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {Object.entries(spend).map(([stage, n]) => (
            <Stat key={stage} label={stage} value={n} />
          ))}
        </dl>
      )}
    </SettingsSection>
  );
}
