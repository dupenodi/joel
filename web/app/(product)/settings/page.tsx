"use client";

import { Field } from "@/components/field";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { getSettings, putSettings } from "@/lib/api";
import { useEffect, useState } from "react";

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
          sync_enabled: s.sync_enabled ? "true" : "false",
          embed_model: s.embed_model,
        });
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load");
        setLoading(false);
      });
  }, []);

  function set(key: string, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setSaved(false);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await putSettings(values);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-muted">
        Loading…
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => void onSave(e)}
      className="mx-auto max-w-2xl space-y-10 px-6 py-10"
    >
      <PageHeader
        title="Settings"
        description="Models and ingestion pause. Tools live on Integrations."
      />
      {error && <p className="text-sm text-accent">{error}</p>}
      {saved && <p className="text-sm text-[var(--ok)]">Saved.</p>}

      <Section title="LLM">
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
        <div className="grid gap-4 sm:grid-cols-2">
          {(
            [
              ["llm_model_distill", "Distill"],
              ["llm_model_answer", "Answer"],
              ["llm_model_extract", "Extract"],
              ["llm_model_resolve", "Resolve"],
              ["llm_model_rerank", "Rerank"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <Input
                value={values[key] ?? ""}
                onChange={(e) => set(key, e.target.value)}
              />
            </Field>
          ))}
        </div>
      </Section>

      <Section title="Sync">
        <label className="flex items-center justify-between gap-4 rounded-[var(--radius-sm)] border border-[var(--line)] bg-surface px-4 py-3">
          <div>
            <p className="text-sm font-medium">Pause ingestion</p>
            <p className="text-xs text-muted">
              Stops the scheduler without disconnecting tools
            </p>
          </div>
          <Checkbox
            checked={values.sync_enabled === "false"}
            onChange={(e) =>
              set("sync_enabled", e.target.checked ? "false" : "true")
            }
          />
        </label>
      </Section>

      <Section title="Embeddings">
        <Field
          label="Embed model"
          hint="Changing this triggers a full re-embed from canonical JSONL."
        >
          <Input
            value={values.embed_model ?? ""}
            onChange={(e) => set("embed_model", e.target.value)}
          />
        </Field>
      </Section>

      <Button type="submit">Save</Button>
    </form>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <h2 className="text-xs font-medium uppercase tracking-[0.06em] text-muted">
        {title}
      </h2>
      {children}
    </section>
  );
}
