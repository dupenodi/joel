"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { getSettings, putSettings } from "@/lib/api";
import { useEffect, useState } from "react";

const MODEL_FIELDS = [
  ["llm_model_distill", "Distill"],
  ["llm_model_answer", "Answer"],
  ["llm_model_extract", "Extract"],
  ["llm_model_resolve", "Resolve"],
  ["llm_model_rerank", "Rerank"],
] as const;

export function ModelsPanel() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) => {
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
    setSaved(false);
    setError(null);
  }

  if (!loaded) return <SettingsSkeleton />;

  return (
    <SettingsSection
      title="Models"
      description="Provider endpoint and which model each pipeline stage uses."
    >
      <div className="space-y-3">
        <p className="text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          Provider
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

        <p className="pt-2 text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          Stages
        </p>
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

        <p className="pt-2 text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          Embeddings
        </p>
        <Field
          label="Embed model"
          hint="Changing this re-embeds the whole corpus."
        >
          <Input
            value={values.embed_model ?? ""}
            onChange={(e) => set("embed_model", e.target.value)}
          />
        </Field>
      </div>

      {error && <p className="mt-3 text-[13px] text-red">{error}</p>}
      <Button
        className="mt-4"
        type="button"
        variant="accent"
        size="sm"
        loading={saving}
        onClick={() => {
          setSaving(true);
          setError(null);
          void putSettings(values)
            .then(() => setSaved(true))
            .catch((e: unknown) => {
              setError(e instanceof Error ? e.message : "Save failed");
            })
            .finally(() => setSaving(false));
        }}
      >
        {saved ? "Saved" : "Save"}
      </Button>
    </SettingsSection>
  );
}
