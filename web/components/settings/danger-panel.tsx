"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { getProfile, wipeOrg } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export function DangerPanel() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [wipeConfirm, setWipeConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return <SettingsSkeleton />;
  if (!profile) return null;

  const domain = profile.org.domain;

  return (
    <SettingsSection
      title="Wipe this workspace"
      description={
        <>
          Deletes indexed data and conversations. People in this workspace stay.
          Type <strong className="text-ink">{domain}</strong> to confirm.
        </>
      }
      danger
    >
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Confirm domain" className="max-w-xs flex-1">
          <Input
            className="bg-surface"
            value={wipeConfirm}
            onChange={(e) => setWipeConfirm(e.target.value)}
            placeholder={domain}
          />
        </Field>
        <Button
          type="button"
          size="sm"
          variant="danger"
          loading={busy}
          className="enabled:bg-red enabled:text-white enabled:shadow-none enabled:hover:bg-red enabled:hover:opacity-90"
          disabled={wipeConfirm !== domain}
          onClick={() => {
            setBusy(true);
            void wipeOrg(domain)
              .then(() => router.push("/"))
              .finally(() => setBusy(false));
          }}
        >
          Wipe
        </Button>
      </div>
    </SettingsSection>
  );
}
