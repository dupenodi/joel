"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { VoiceFields } from "@/components/settings/voice-fields";
import { WorkspaceAvatar } from "@/components/settings/workspace-avatar";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getSettings, getWorkspace, patchWorkspace, putSettings } from "@/lib/api";
import type { Me, Workspace } from "@/lib/types";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

export function GeneralPanel() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [memberCount, setMemberCount] = useState(0);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [about, setAbout] = useState("");
  const [voice, setVoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [data, settings] = await Promise.all([getWorkspace(), getSettings()]);
    setWorkspace(data.workspace);
    setMe(data.me);
    setMemberCount(data.members.length);
    setName(data.workspace.name);
    setDomain(data.workspace.domain);
    setAbout(settings.workspace_about ?? "");
    setVoice(settings.voice ?? "");
  }, []);

  useEffect(() => {
    void reload().catch(() => {});
  }, [reload]);

  if (!workspace || !me) return null;

  const admin = Boolean(me.is_admin || me.role === "owner" || me.role === "admin");

  return (
    <SettingsSection
      title="General"
      description="This company's name, a short about, and how joel talks."
    >
      <div className="mb-5 flex items-center gap-3 rounded-card bg-field p-3">
        <WorkspaceAvatar
          name={workspace.name}
          logoUrl={workspace.logo_url}
          size={48}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-medium text-ink">
            {workspace.name}
          </p>
          <p className="truncate text-[12.5px] text-ink-3">
            {workspace.domain} · {memberCount}{" "}
            {memberCount === 1 ? "person" : "people"}
          </p>
        </div>
        <Link
          href="/settings/members"
          className="shrink-0 text-[13px] font-medium text-ink-2 underline-offset-2 hover:text-ink hover:underline"
        >
          Manage members
        </Link>
      </div>

      {admin ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            setSaved(false);
            void Promise.all([
              patchWorkspace({ name, domain }),
              putSettings({ workspace_about: about, voice }),
            ])
              .then(([res]) => {
                setWorkspace(res.workspace);
                setName(res.workspace.name);
                setDomain(res.workspace.domain);
                setSaved(true);
              })
              .catch((err: unknown) => {
                setError(err instanceof Error ? err.message : "Could not save");
              })
              .finally(() => setBusy(false));
          }}
        >
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <Field
            label="Domain"
            hint="Used for the workspace mark (favicon) and wipe confirmation."
          >
            <Input
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <Field
            label="About"
            hint="Optional. What this company is, in the owner's words — not a website scrape."
          >
            <Textarea
              value={about}
              placeholder="We build …"
              onChange={(e) => {
                setAbout(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <VoiceFields
            value={voice}
            onChange={(next) => {
              setVoice(next);
              setSaved(false);
              setError(null);
            }}
          />
          {error && <p className="text-[13px] text-red">{error}</p>}
          <Button type="submit" size="sm" variant="accent" loading={busy}>
            {saved ? "Saved" : "Save"}
          </Button>
        </form>
      ) : (
        <p className="text-[13px] text-ink-2">
          Only an owner or admin can rename this workspace.
        </p>
      )}
    </SettingsSection>
  );
}
