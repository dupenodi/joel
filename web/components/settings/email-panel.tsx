"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { SettingsSection } from "@/components/settings/settings-section";
import { SettingsSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { getSettings, putSettings, testOutboundEmail } from "@/lib/api";
import { useEffect, useState } from "react";

const SELECT_CLASS =
  "h-9 w-full rounded-control bg-field px-2.5 text-[14px] text-ink shadow-hairline outline-none transition-colors duration-150 hover:bg-hover focus:bg-surface focus:shadow-btn";

type MailProvider = "none" | "smtp" | "resend";

export function EmailPanel() {
  const [provider, setProvider] = useState<MailProvider>("none");
  const [from, setFrom] = useState("");
  const [fromName, setFromName] = useState("joel");
  const [appUrl, setAppUrl] = useState("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpPasswordSet, setSmtpPasswordSet] = useState(false);
  const [smtpTls, setSmtpTls] = useState(true);
  const [resendKey, setResendKey] = useState("");
  const [resendKeySet, setResendKeySet] = useState(false);
  const [testTo, setTestTo] = useState("");

  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testOk, setTestOk] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) => {
        const p = (s.mail_provider ?? "none") as MailProvider;
        setProvider(p === "smtp" || p === "resend" ? p : "none");
        setFrom(s.mail_from ?? "");
        setFromName(s.mail_from_name ?? "joel");
        setAppUrl(s.mail_app_url ?? "");
        setSmtpHost(s.mail_smtp_host ?? "");
        setSmtpPort(s.mail_smtp_port ?? "587");
        setSmtpUser(s.mail_smtp_user ?? "");
        setSmtpPasswordSet(Boolean(s.mail_smtp_password_set));
        setSmtpTls((s.mail_smtp_tls ?? "true") !== "false");
        setResendKeySet(Boolean(s.mail_resend_api_key_set));
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return <SettingsSkeleton />;

  const configured = provider !== "none";

  return (
    <div className="space-y-6">
      <SettingsSection
        title="Outbound email"
        description="Optional. When configured, invite emails are sent automatically. Installs still work link-only without a provider."
        headerAside={
          <span
            className={
              configured
                ? "inline-flex h-6 items-center rounded-full bg-green-tint px-2.5 text-[11.5px] font-medium text-green"
                : "inline-flex h-6 items-center rounded-full bg-field px-2.5 text-[11.5px] font-medium text-ink-3"
            }
          >
            {configured ? "Sending" : "Link-only"}
          </span>
        }
      >
        <div className="space-y-3">
          <Field label="Provider">
            <select
              aria-label="Email provider"
              className={SELECT_CLASS}
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value as MailProvider);
                setSaved(false);
                setTestOk(null);
                setError(null);
              }}
            >
              <option value="none">None (copy invite links)</option>
              <option value="smtp">SMTP</option>
              <option value="resend">Resend</option>
            </select>
          </Field>

          {provider !== "none" && (
            <>
              <Field label="From address">
                <Input
                  type="email"
                  value={from}
                  placeholder="joel@yourco.dev"
                  onChange={(e) => {
                    setFrom(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
              <Field label="From name">
                <Input
                  value={fromName}
                  placeholder="joel"
                  onChange={(e) => {
                    setFromName(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
              <Field
                label="App URL"
                hint="Used in invite links inside emails. Leave blank to use this browser’s origin."
              >
                <Input
                  value={appUrl}
                  placeholder="https://joel.yourco.dev"
                  onChange={(e) => {
                    setAppUrl(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
            </>
          )}

          {provider === "smtp" && (
            <>
              <p className="pt-1 text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
                SMTP
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="sm:col-span-2">
                  <Field label="Host">
                    <Input
                      value={smtpHost}
                      placeholder="smtp.resend.com"
                      onChange={(e) => {
                        setSmtpHost(e.target.value);
                        setSaved(false);
                      }}
                    />
                  </Field>
                </div>
                <Field label="Port">
                  <Input
                    value={smtpPort}
                    placeholder="587"
                    onChange={(e) => {
                      setSmtpPort(e.target.value);
                      setSaved(false);
                    }}
                  />
                </Field>
              </div>
              <Field label="Username">
                <Input
                  value={smtpUser}
                  placeholder="resend"
                  onChange={(e) => {
                    setSmtpUser(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
              <Field
                label="Password"
                hint={
                  smtpPasswordSet
                    ? "Leave blank to keep the current password"
                    : undefined
                }
              >
                <Input
                  type="password"
                  value={smtpPassword}
                  placeholder={smtpPasswordSet ? "••••••••" : ""}
                  onChange={(e) => {
                    setSmtpPassword(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
              <label className="flex items-center gap-2 text-[13px] text-ink-2">
                <input
                  type="checkbox"
                  checked={smtpTls}
                  onChange={(e) => {
                    setSmtpTls(e.target.checked);
                    setSaved(false);
                  }}
                  className="size-3.5 rounded border-line"
                />
                STARTTLS (uncheck for port 465 SSL)
              </label>
            </>
          )}

          {provider === "resend" && (
            <>
              <p className="pt-1 text-[12px] font-medium tracking-[0.04em] text-ink-3 uppercase">
                Resend
              </p>
              <Field
                label="API key"
                hint={
                  resendKeySet
                    ? "Leave blank to keep the current key"
                    : undefined
                }
              >
                <Input
                  type="password"
                  value={resendKey}
                  placeholder={resendKeySet ? "re_…" : "re_…"}
                  onChange={(e) => {
                    setResendKey(e.target.value);
                    setSaved(false);
                  }}
                />
              </Field>
            </>
          )}

          {error && <p className="text-[13px] text-red">{error}</p>}
          {saved && !error && (
            <p className="text-[13px] text-green">Saved.</p>
          )}

          <div className="flex justify-end pt-1">
            <Button
              type="button"
              size="sm"
              variant="accent"
              loading={saving}
              onClick={() => {
                setSaving(true);
                setError(null);
                setSaved(false);
                setTestOk(null);
                const values: Record<string, string> = {
                  mail_provider: provider,
                  mail_from: from,
                  mail_from_name: fromName,
                  mail_app_url: appUrl,
                  mail_smtp_host: smtpHost,
                  mail_smtp_port: smtpPort,
                  mail_smtp_user: smtpUser,
                  mail_smtp_tls: smtpTls ? "true" : "false",
                };
                if (smtpPassword.trim()) {
                  values.mail_smtp_password = smtpPassword.trim();
                }
                if (resendKey.trim()) {
                  values.mail_resend_api_key = resendKey.trim();
                }
                void putSettings(values)
                  .then(() => {
                    setSaved(true);
                    setSmtpPassword("");
                    setResendKey("");
                    if (smtpPassword.trim()) setSmtpPasswordSet(true);
                    if (resendKey.trim()) setResendKeySet(true);
                  })
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error ? err.message : "Could not save",
                    );
                  })
                  .finally(() => setSaving(false));
              }}
            >
              Save
            </Button>
          </div>
        </div>
      </SettingsSection>

      {provider !== "none" && (
        <SettingsSection
          title="Send test"
          description="Verify delivery before inviting the team."
        >
          <div className="space-y-3">
            <Field label="Recipient" hint="Defaults to your account email">
              <Input
                type="email"
                value={testTo}
                placeholder="you@yourco.dev"
                onChange={(e) => setTestTo(e.target.value)}
              />
            </Field>
            {testOk && <p className="text-[13px] text-green">{testOk}</p>}
            {error && <p className="text-[13px] text-red">{error}</p>}
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                loading={testing}
                onClick={() => {
                  setTesting(true);
                  setError(null);
                  setTestOk(null);
                  void testOutboundEmail(testTo.trim() || undefined)
                    .then((res) => {
                      setTestOk(`Sent via ${res.provider}.`);
                    })
                    .catch((err: unknown) => {
                      setError(
                        err instanceof Error
                          ? err.message
                          : "Test send failed",
                      );
                    })
                    .finally(() => setTesting(false));
                }}
              >
                Send test email
              </Button>
            </div>
          </div>
        </SettingsSection>
      )}
    </div>
  );
}
