"use client";

import { Switch } from "@/components/beautifului/primitives/switch";
import { PauseToggleSkeleton, SettingsSkeleton } from "@/components/skeletons";
import { Field } from "@/components/field";
import { Stat } from "@/components/stat";
import { Button } from "@/components/beautifului/primitives/button";
import { Input } from "@/components/ui/input";
import {
  getProfile,
  getSettings,
  putProfile,
  putSettings,
  wipeOrg,
} from "@/lib/api";
import type { Profile } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const MODEL_FIELDS = [
  ["llm_model_distill", "Distill"],
  ["llm_model_answer", "Answer"],
  ["llm_model_extract", "Extract"],
  ["llm_model_resolve", "Resolve"],
  ["llm_model_rerank", "Rerank"],
] as const;

export function PauseToggle() {
  const [enabled, setEnabled] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setEnabled(s.sync_enabled);
        setReady(true);
      })
      .catch(() => {
        setReady(true);
      });
  }, []);

  if (!ready) return <PauseToggleSkeleton />;

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

/** Name, models, spend, wipe — Settings, not the Integrations grid. */
export function InstallPanel() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [wipeConfirm, setWipeConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorAt, setErrorAt] = useState<"name" | "models" | null>(null);
  const [saving, setSaving] = useState<"name" | "models" | null>(null);
  const [saved, setSaved] = useState<"name" | "models" | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([getProfile(), getSettings()])
      .then(([p, s]) => {
        setProfile(p);
        if (p) setName(p.display_name);
        setValues({
          llm_base_url: s.raw?.llm_base_url ?? s.llm_base_url,
          llm_api_key: "",
          llm_model_distill: s.llm_model_distill,
          llm_model_extract: s.llm_model_extract,
          llm_model_answer: s.llm_model_answer,
          llm_model_resolve: s.llm_model_resolve,
          llm_model_rerank: s.llm_model_rerank,
          embed_model: s.embed_model,
        });
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  function set(key: string, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setSaved(null);
    setError(null);
    setErrorAt(null);
  }

  async function onSaveModels() {
    setError(null);
    setErrorAt(null);
    setSaving("models");
    try {
      await putSettings(values);
      setSaved("models");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setErrorAt("models");
    } finally {
      setSaving(null);
    }
  }

  async function onSaveName() {
    setError(null);
    setErrorAt(null);
    setSaving("name");
    try {
      await putProfile(name.trim() || "You");
      setSaved("name");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setErrorAt("name");
    } finally {
      setSaving(null);
    }
  }

  const spend = profile?.spend_30d ?? {};
  const spendTotal = Object.values(spend).reduce((a, n) => a + n, 0);

  if (!loaded) return <SettingsSkeleton />;

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          You
        </h2>
        <p className="text-[13px] leading-relaxed text-ink-2">
          Shown on Home.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Display name" className="min-w-48 flex-1">
            <Input
              value={name}
              placeholder="Your name"
              onChange={(e) => {
                setName(e.target.value);
                setSaved(null);
                setError(null);
                setErrorAt(null);
              }}
            />
          </Field>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            loading={saving === "name"}
            onClick={() => void onSaveName()}
          >
            {saved === "name" ? "Saved" : "Save"}
          </Button>
        </div>
        {errorAt === "name" && error && (
          <p className="text-[13px] text-red">{error}</p>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          Models
        </h2>
        <p className="text-[13px] leading-relaxed text-ink-2">
          Base URL, API key, and which model each stage uses.
        </p>
        <Field label="Base URL">
          <Input
            value={values.llm_base_url ?? ""}
            onChange={(e) => set("llm_base_url", e.target.value)}
          />
        </Field>
        <Field label="API key" hint="Leave blank to keep the current key">
          <Input
            type="password"
            placeholder="sk-…"
            value={values.llm_api_key ?? ""}
            onChange={(e) => set("llm_api_key", e.target.value)}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          {MODEL_FIELDS.map(([key, label]) => (
            <Field key={key} label={label}>
              <Input
                value={values[key] ?? ""}
                onChange={(e) => set(key, e.target.value)}
              />
            </Field>
          ))}
        </div>
        <Field
          label="Embed model"
          hint="Changing this re-embeds the whole corpus."
        >
          <Input
            value={values.embed_model ?? ""}
            onChange={(e) => set("embed_model", e.target.value)}
          />
        </Field>
        {errorAt === "models" && error && (
          <p className="text-[13px] text-red">{error}</p>
        )}
        <Button
          type="button"
          variant="accent"
          loading={saving === "models"}
          disabled={!loaded}
          onClick={() => void onSaveModels()}
        >
          {saved === "models" ? "Saved" : "Save"}
        </Button>
      </section>

      {spendTotal > 0 && (
        <section>
          <h2 className="mb-2 text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
            LLM calls · 30d
          </h2>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {Object.entries(spend).map(([stage, n]) => (
              <Stat key={stage} label={stage} value={n} />
            ))}
          </dl>
        </section>
      )}

      {profile && (
        <div className="rounded-card bg-red-tint p-3">
          <h2 className="text-[14px] font-medium text-red">Wipe this install</h2>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
            Deletes indexed data and conversations. People in this workspace stay.
            Type{" "}
            <strong className="text-ink">{profile.org.domain}</strong> to confirm.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Field label="Confirm domain" className="max-w-xs flex-1">
              <Input
                className="bg-surface"
                value={wipeConfirm}
                onChange={(e) => setWipeConfirm(e.target.value)}
                placeholder={profile.org.domain}
              />
            </Field>
            <Button
              type="button"
              variant="danger"
              disabled={wipeConfirm !== profile.org.domain}
              onClick={async () => {
                await wipeOrg(profile.org.domain);
                router.push("/");
              }}
            >
              Wipe
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
