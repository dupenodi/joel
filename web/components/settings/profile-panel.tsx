"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { PersonAvatar } from "@/components/settings/workspace-avatar";
import { SettingsSection } from "@/components/settings/settings-section";
import { Input } from "@/components/ui/input";
import { changePassword, getWorkspace, logout, putProfile } from "@/lib/api";
import type { Me } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export function ProfilePanel() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwSaved, setPwSaved] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);

  useEffect(() => {
    void getWorkspace()
      .then((data) => {
        setMe(data.me);
        setName(data.me.display_name);
      })
      .catch(() => {});
  }, []);

  if (!me) return null;

  return (
    <div className="space-y-6">
      <SettingsSection
        title="Profile"
        description="How you appear in this workspace."
      >
        <div className="mb-5 flex items-center gap-3">
          <PersonAvatar name={name || me.display_name} size={44} />
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium text-ink">
              {name || me.display_name}
            </p>
            <p className="truncate text-[12.5px] text-ink-3">{me.email}</p>
          </div>
        </div>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setSaving(true);
            setError(null);
            setSaved(false);
            void putProfile(name.trim() || "You")
              .then(() => {
                setSaved(true);
                setMe((prev) =>
                  prev ? { ...prev, display_name: name.trim() || "You" } : prev,
                );
              })
              .catch((err: unknown) => {
                setError(err instanceof Error ? err.message : "Save failed");
              })
              .finally(() => setSaving(false));
          }}
        >
          <Field label="Display name">
            <Input
              value={name}
              placeholder="Your name"
              onChange={(e) => {
                setName(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <Field label="Email" hint="Tied to your account — not editable here.">
            <Input value={me.email} disabled readOnly />
          </Field>
          {error && <p className="text-[13px] text-red">{error}</p>}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button type="submit" size="sm" variant="accent" loading={saving}>
              {saved ? "Saved" : "Save"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                void logout().then(() => router.replace("/login"));
              }}
            >
              Sign out
            </Button>
          </div>
        </form>
      </SettingsSection>

      <SettingsSection
        title="Password"
        description="Change the password you use to sign in."
      >
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setPwSaving(true);
            setPwError(null);
            setPwSaved(false);
            void changePassword(currentPassword, newPassword)
              .then(() => {
                setPwSaved(true);
                setCurrentPassword("");
                setNewPassword("");
              })
              .catch((err: unknown) => {
                setPwError(
                  err instanceof Error ? err.message : "Could not change password",
                );
              })
              .finally(() => setPwSaving(false));
          }}
        >
          <Field label="Current password">
            <Input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => {
                setCurrentPassword(e.target.value);
                setPwSaved(false);
              }}
            />
          </Field>
          <Field label="New password" hint="At least 8 characters.">
            <Input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value);
                setPwSaved(false);
              }}
            />
          </Field>
          {pwError && <p className="text-[13px] text-red">{pwError}</p>}
          {pwSaved && !pwError && (
            <p className="text-[13px] text-green">Password updated.</p>
          )}
          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              size="sm"
              variant="accent"
              loading={pwSaving}
              disabled={
                currentPassword.length === 0 || newPassword.length < 8
              }
            >
              Update password
            </Button>
          </div>
        </form>
      </SettingsSection>
    </div>
  );
}
