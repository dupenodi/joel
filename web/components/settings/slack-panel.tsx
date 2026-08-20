"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { CopyButton } from "@/components/beautifului/primitives/copy-button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { getSettings, putSettings } from "@/lib/api";
import { integrationLogoUrl } from "@/lib/integrations";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

export function SlackPanel() {
  const [secret, setSecret] = useState("");
  const [token, setToken] = useState("");
  const [secretSet, setSecretSet] = useState(false);
  const [tokenSet, setTokenSet] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventsUrl = useMemo(() => {
    if (typeof window === "undefined") return "/api/slack/events";
    return `${window.location.origin}/api/slack/events`;
  }, []);

  const manifestUrl = useMemo(() => {
    if (typeof window === "undefined") return "/slack-app-manifest.yaml";
    return `${window.location.origin}/slack-app-manifest.yaml`;
  }, []);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSecretSet(Boolean(s.slack_signing_secret_set));
        setTokenSet(Boolean(s.slack_bot_token_set));
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return <SettingsSkeleton />;

  const connected = secretSet && tokenSet;

  return (
    <div className="space-y-6">
      <div className="rounded-card bg-surface p-5 shadow-card">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span
              className="inline-flex size-10 items-center justify-center rounded-control shadow-hairline"
              style={{ background: "#4A154B" }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={integrationLogoUrl("slack")}
                alt=""
                width={22}
                height={22}
                className="rounded-[3px]"
              />
            </span>
            <div>
              <h2 className="text-[15px] font-semibold tracking-tight text-ink">
                Slack bot
              </h2>
              <p className="mt-1 max-w-md text-[13px] leading-relaxed text-ink-2">
                Create your own Slack app from the manifest, paste the signing
                secret and bot token, then{" "}
                <code className="rounded-[4px] bg-field px-1 py-0.5 text-[12px]">
                  /invite @joel
                </code>{" "}
                in the channels where it should answer @mentions. We don&apos;t
                create channels or post a launch message.
              </p>
            </div>
          </div>
          <span
            className={
              connected
                ? "inline-flex h-6 items-center rounded-full bg-green-tint px-2.5 text-[11.5px] font-medium text-green"
                : "inline-flex h-6 items-center rounded-full bg-field px-2.5 text-[11.5px] font-medium text-ink-3"
            }
          >
            {connected ? "Connected" : "Not configured"}
          </span>
        </div>

        <ol className="mb-5 space-y-2.5 rounded-card bg-field p-4 text-[13px] text-ink-2">
          <li className="flex gap-2.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[11px] font-semibold text-ink shadow-hairline">
              1
            </span>
            <span className="min-w-0">
              Create a Slack app from the manifest (
              <a
                href="https://api.slack.com/apps"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-ink underline-offset-2 hover:underline"
              >
                api.slack.com/apps
              </a>
              {" "}
              → From a manifest).{" "}
              <a
                href={manifestUrl}
                className="font-medium text-ink underline-offset-2 hover:underline"
              >
                Download
              </a>
              <CopyButton
                className="ml-1.5 align-middle"
                label="Copy manifest"
                text={async () => {
                  const res = await fetch(manifestUrl);
                  return res.text();
                }}
              />
            </span>
          </li>
          <li className="flex gap-2.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[11px] font-semibold text-ink shadow-hairline">
              2
            </span>
            <span className="min-w-0">
              Set Event Subscriptions Request URL to{" "}
              <code className="break-all rounded-[4px] bg-surface px-1 py-0.5 text-[12px] text-ink">
                {eventsUrl}
              </code>
              <CopyButton
                className="ml-1.5 align-middle"
                text={eventsUrl}
              />
            </span>
          </li>
          <li className="flex gap-2.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[11px] font-semibold text-ink shadow-hairline">
              3
            </span>
            <span>
              Install the app to your Slack workspace, then paste the Signing
              Secret and Bot User OAuth Token below.
            </span>
          </li>
          <li className="flex gap-2.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[11px] font-semibold text-ink shadow-hairline">
              4
            </span>
            <span>
              In each channel,{" "}
              <code className="rounded-[4px] bg-surface px-1 py-0.5 text-[12px] text-ink">
                /invite @joel
              </code>
              . Mentions are the only reply path.
            </span>
          </li>
        </ol>

        <div className="space-y-3">
          <Field
            label="Signing secret"
            hint={
              secretSet
                ? "A secret is already set. Leave blank to keep it."
                : undefined
            }
          >
            <Input
              type="password"
              placeholder={
                secretSet ? "•••••••••••••" : "Paste from Slack app settings"
              }
              value={secret}
              onChange={(e) => {
                setSecret(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <Field
            label="Bot token"
            hint={
              tokenSet
                ? "A token is already set. Leave blank to keep it."
                : "Starts with xoxb-"
            }
          >
            <Input
              type="password"
              placeholder={tokenSet ? "•••••••••••••" : "xoxb-…"}
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setSaved(false);
                setError(null);
              }}
            />
          </Field>
          <Button
            type="button"
            size="sm"
            variant="accent"
            loading={saving}
            onClick={() => {
              setSaving(true);
              setError(null);
              void putSettings({
                slack_signing_secret: secret,
                slack_bot_token: token,
              })
                .then(() => {
                  if (secret) setSecretSet(true);
                  if (token) setTokenSet(true);
                  setSecret("");
                  setToken("");
                  setSaved(true);
                })
                .catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : "Save failed");
                })
                .finally(() => setSaving(false));
            }}
          >
            {saved ? "Saved" : "Save"}
          </Button>
        </div>
        {error && <p className="mt-3 text-[13px] text-red">{error}</p>}
      </div>

      <SettingsSection
        title="Also ingest Slack?"
        description="Connecting Slack as a connector syncs channels into memory. That’s separate from the bot being in the room."
      >
        <Link
          href="/integrations?open=slack"
          className="text-[13.5px] font-medium text-ink underline-offset-2 hover:underline"
        >
          Open Slack on Integrations →
        </Link>
      </SettingsSection>
    </div>
  );
}
