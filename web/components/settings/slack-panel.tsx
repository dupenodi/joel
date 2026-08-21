"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { CopyButton } from "@/components/beautifului/primitives/copy-button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { disconnectSlack, getSettings, putSettings } from "@/lib/api";
import { integrationLogoUrl } from "@/lib/integrations";
import type { Settings } from "@/lib/types";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

export function SlackPanel() {
  const pathname = usePathname();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [secret, setSecret] = useState("");
  const [token, setToken] = useState("");
  const [secretSet, setSecretSet] = useState(false);
  const [tokenSet, setTokenSet] = useState(false);
  const [connected, setConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventsUrl = useMemo(() => {
    if (typeof window === "undefined") return "/api/slack/events";
    return `${window.location.origin}/api/slack/events`;
  }, []);

  const interactionsUrl = useMemo(() => {
    if (typeof window === "undefined") return "/api/slack/interactions";
    return `${window.location.origin}/api/slack/interactions`;
  }, []);

  const manifestUrl = useMemo(() => {
    if (typeof window === "undefined") return "/slack-app-manifest.yaml";
    return `${window.location.origin}/slack-app-manifest.yaml`;
  }, []);

  const returnTo = pathname.startsWith("/onboarding")
    ? "/onboarding/slack"
    : "/settings/slack";

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setSecretSet(Boolean(s.slack_signing_secret_set));
        setTokenSet(Boolean(s.slack_bot_token_set));
        setConnected(Boolean(s.slack_connected));
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const result = new URLSearchParams(window.location.search).get("slack");
    if (result === "ok") {
      setConnected(true);
      setTokenSet(true);
    } else if (result === "denied") {
      setError("Slack install was cancelled.");
    } else if (result === "error") {
      setError("Couldn't connect Slack. Try again.");
    }
  }, []);

  if (!loaded) return <SettingsSkeleton />;

  const install = settings?.slack_install ?? "manifest";

  return (
    <div className="space-y-6">
      <div className="rounded-card bg-surface p-5 shadow-card">
        <SlackHeader connected={connected} install={install} />

        {install === "oauth" && (
          <OAuthInstall
            connected={connected}
            returnTo={returnTo}
            disconnecting={saving}
            error={error}
            onDisconnect={() => {
              setSaving(true);
              setError(null);
              void disconnectSlack()
                .then(() => {
                  setConnected(false);
                  setTokenSet(false);
                  setSecretSet(false);
                })
                .catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : "Disconnect failed");
                })
                .finally(() => setSaving(false));
            }}
          />
        )}

        {install === "unavailable" && (
          <p className="text-[13px] leading-relaxed text-ink-2">
            Slack isn&apos;t available on this hosted install yet.
          </p>
        )}

        {install === "manifest" && (
          <ManifestInstall
            eventsUrl={eventsUrl}
            interactionsUrl={interactionsUrl}
            manifestUrl={manifestUrl}
            secret={secret}
            token={token}
            secretSet={secretSet}
            tokenSet={tokenSet}
            saving={saving}
            saved={saved}
            error={error}
            onSecret={(value) => {
              setSecret(value);
              setSaved(false);
              setError(null);
            }}
            onToken={(value) => {
              setToken(value);
              setSaved(false);
              setError(null);
            }}
            onSave={() => {
              setSaving(true);
              setError(null);
              void putSettings({
                slack_signing_secret: secret,
                slack_bot_token: token,
              })
                .then(() => {
                  if (secret) setSecretSet(true);
                  if (token) setTokenSet(true);
                  if (secret && token) setConnected(true);
                  setSecret("");
                  setToken("");
                  setSaved(true);
                })
                .catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : "Save failed");
                })
                .finally(() => setSaving(false));
            }}
          />
        )}
      </div>

      <SettingsSection
        title="Also ingest Slack?"
        description="Syncs channels into memory. Separate from the bot answering in them."
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

function SlackHeader({
  connected,
  install,
}: {
  connected: boolean;
  install: string;
}) {
  const oauth = install === "oauth";
  return (
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
            {oauth
              ? "Add joel, then /invite @joel where it should answer. Nothing is posted."
              : install === "unavailable"
                ? "The hosted Slack app isn't configured yet."
                : "Create an app from the manifest, paste both secrets, then /invite @joel where it should answer."}
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
  );
}

function OAuthInstall({
  connected,
  returnTo,
  disconnecting,
  error,
  onDisconnect,
}: {
  connected: boolean;
  returnTo: string;
  disconnecting: boolean;
  error: string | null;
  onDisconnect: () => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-[13px] leading-relaxed text-ink-2">
        After connecting, in each channel run{" "}
        <code className="rounded-[4px] bg-field px-1 py-0.5 text-[12px] text-ink">
          /invite @joel
        </code>
        . Mentions are the only reply path.
      </p>
      {connected ? (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          loading={disconnecting}
          onClick={onDisconnect}
        >
          Disconnect
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="accent"
          onClick={() => {
            window.location.href = `/api/slack/oauth/start?return_to=${encodeURIComponent(returnTo)}`;
          }}
        >
          Add to Slack
        </Button>
      )}
      {error && <p className="text-[13px] text-red">{error}</p>}
    </div>
  );
}

function ManifestInstall({
  eventsUrl,
  interactionsUrl,
  manifestUrl,
  secret,
  token,
  secretSet,
  tokenSet,
  saving,
  saved,
  error,
  onSecret,
  onToken,
  onSave,
}: {
  eventsUrl: string;
  interactionsUrl: string;
  manifestUrl: string;
  secret: string;
  token: string;
  secretSet: boolean;
  tokenSet: boolean;
  saving: boolean;
  saved: boolean;
  error: string | null;
  onSecret: (value: string) => void;
  onToken: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <>
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
            </a>{" "}
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
            <CopyButton className="ml-1.5 align-middle" text={eventsUrl} />
            {" "}and Interactivity Request URL to{" "}
            <code className="break-all rounded-[4px] bg-surface px-1 py-0.5 text-[12px] text-ink">
              {interactionsUrl}
            </code>
            <CopyButton className="ml-1.5 align-middle" text={interactionsUrl} />
            {" "}(both are in the manifest).
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
            secretSet ? "A secret is already set. Leave blank to keep it." : undefined
          }
        >
          <Input
            type="password"
            placeholder={
              secretSet ? "•••••••••••••" : "Paste from Slack app settings"
            }
            value={secret}
            onChange={(e) => onSecret(e.target.value)}
          />
        </Field>
        <Field
          label="Bot token"
          hint={tokenSet ? "A token is already set. Leave blank to keep it." : "Starts with xoxb-"}
        >
          <Input
            type="password"
            placeholder={tokenSet ? "•••••••••••••" : "xoxb-…"}
            value={token}
            onChange={(e) => onToken(e.target.value)}
          />
        </Field>
        <Button
          type="button"
          size="sm"
          variant="accent"
          loading={saving}
          onClick={onSave}
        >
          {saved ? "Saved" : "Save"}
        </Button>
      </div>
      {error && <p className="mt-3 text-[13px] text-red">{error}</p>}
    </>
  );
}
