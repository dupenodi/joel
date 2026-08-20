"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { createApiKey, listApiKeys, revokeApiKey } from "@/lib/api";
import type { ApiKey } from "@/lib/types";
import { formatRelative } from "@/lib/utils";
import { useEffect, useState } from "react";

/** §13's MCP surface: a key maps to exactly one person -- your own
 * normal permissions, not a separate privilege model. Shown once, on
 * creation, then only its last 4 characters ever again. */
export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listApiKeys()
      .then(setKeys)
      .catch(() => setKeys([]));
  }

  useEffect(reload, []);

  async function onCreate() {
    setError(null);
    setCreating(true);
    try {
      const { key } = await createApiKey(label.trim() || "API key");
      setRevealed(key);
      setLabel("");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create key");
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(id: string) {
    await revokeApiKey(id).catch(() => {});
    reload();
  }

  if (keys === null) return null;

  return (
    <section className="rounded-card bg-surface p-5 shadow-card">
      <div className="mb-4">
        <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
          API keys
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
          For MCP clients (Claude Desktop, Claude Code, ...) — connect to{" "}
          <code className="rounded-[4px] bg-field px-1 py-0.5 text-[12px]">/mcp/</code>{" "}
          with a key below. A key answers with your own permissions, nothing more.
        </p>
      </div>

      {revealed && (
        <div className="mb-4 rounded-card bg-field p-3">
          <p className="text-[13px] font-medium text-ink">
            Copy this now — it won&apos;t be shown again.
          </p>
          <code className="mt-1.5 block truncate rounded-[6px] bg-surface px-2 py-1.5 text-[12.5px] text-ink shadow-hairline">
            {revealed}
          </code>
          <Button
            type="button"
            size="sm"
            variant="primary"
            className="mt-2"
            onClick={() => setRevealed(null)}
          >
            Done
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <Field label="Label" className="min-w-48 flex-1">
          <Input
            value={label}
            placeholder="e.g. Claude Desktop"
            onChange={(e) => setLabel(e.target.value)}
          />
        </Field>
        <Button
          type="button"
          size="sm"
          variant="primary"
          loading={creating}
          onClick={() => void onCreate()}
        >
          Create key
        </Button>
      </div>
      {error && <p className="mt-3 text-[13px] text-red">{error}</p>}

      {keys.length > 0 && (
        <ul className="-mx-5 mt-4 divide-y divide-line border-t border-line">
          {keys.map((k) => (
            <li
              key={k.id}
              className="flex items-center justify-between gap-3 px-5 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-[13.5px] text-ink">{k.label}</p>
                <p className="text-[12px] text-ink-3">
                  {"joel_sk_…"}
                  {k.last4} · {k.last_used_at ? `used ${formatRelative(k.last_used_at)}` : "never used"}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="danger"
                className="shrink-0"
                onClick={() => void onRevoke(k.id)}
              >
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
