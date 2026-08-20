"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { SettingsEmpty } from "@/components/settings/settings-section";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createApiKey, listApiKeys, revokeApiKey } from "@/lib/api";
import type { ApiKey } from "@/lib/types";
import { formatRelative } from "@/lib/utils";
import { useEffect, useState } from "react";

export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
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
      setCreateOpen(false);
      setLabel("");
      setCopied(false);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create key");
    } finally {
      setCreating(false);
    }
  }

  if (keys === null) return null;

  return (
    <>
      <div className="rounded-card bg-surface p-5 shadow-card">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="inline-flex size-10 items-center justify-center rounded-control bg-field text-ink shadow-hairline">
              <McpGlyph />
            </span>
            <div>
              <h2 className="text-[15px] font-semibold tracking-tight text-ink">
                MCP API keys
              </h2>
              <p className="mt-1 max-w-md text-[13px] leading-relaxed text-ink-2">
                Connect Claude Desktop, Claude Code, or any MCP client to{" "}
                <code className="rounded-[4px] bg-field px-1 py-0.5 text-[12px]">
                  /mcp/
                </code>
                . A key answers with your own permissions — nothing more.
              </p>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant="accent"
            onClick={() => {
              setError(null);
              setCreateOpen(true);
            }}
          >
            Create key
          </Button>
        </div>

        {keys.length === 0 ? (
          <SettingsEmpty>
            No keys yet. Create one to connect an MCP client.
          </SettingsEmpty>
        ) : (
          <ul className="-mx-5 divide-y divide-line border-t border-line">
            {keys.map((k) => (
              <li
                key={k.id}
                className="flex items-center justify-between gap-3 px-5 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13.5px] font-medium text-ink">
                    {k.label}
                  </p>
                  <p className="text-[12px] text-ink-3">
                    joel_sk_…{k.last4} ·{" "}
                    {k.last_used_at
                      ? `used ${formatRelative(k.last_used_at)}`
                      : "never used"}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="danger"
                  className="shrink-0"
                  onClick={() => {
                    void revokeApiKey(k.id)
                      .catch(() => {})
                      .then(reload);
                  }}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create API key"
      >
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">Create API key</h2>
          <p className="mt-1 text-[13px] text-ink-2">
            Label it so you remember which client it belongs to.
          </p>
        </div>
        <div className="space-y-3 px-5 py-4">
          <Field label="Label">
            <Input
              autoFocus
              value={label}
              placeholder="e.g. Claude Desktop"
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
          {error && <p className="text-[13px] text-red">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              variant="accent"
              loading={creating}
              onClick={() => void onCreate()}
            >
              Create
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(revealed)}
        onClose={() => {
          setRevealed(null);
          setCopied(false);
        }}
        title="API key created"
        locked
      >
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">
            Copy this key now
          </h2>
          <p className="mt-1 text-[13px] text-ink-2">
            It won&apos;t be shown again.
          </p>
        </div>
        <div className="space-y-3 px-5 py-4">
          <code className="block break-all rounded-control bg-field px-3 py-2.5 text-[12.5px] text-ink">
            {revealed}
          </code>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={() => {
                if (!revealed) return;
                void navigator.clipboard.writeText(revealed).then(() => {
                  setCopied(true);
                });
              }}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="accent"
              onClick={() => {
                setRevealed(null);
                setCopied(false);
              }}
            >
              Done
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

function McpGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 4h8v3.5a2.5 2.5 0 0 1-2.5 2.5h-3A2.5 2.5 0 0 1 8 7.5V4Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M12 10v4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <rect
        x="6"
        y="14"
        width="12"
        height="6"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}
