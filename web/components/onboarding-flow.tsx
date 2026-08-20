"use client";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { ApiKeysPanel } from "@/components/settings/api-keys-panel";
import { MembersPanel } from "@/components/settings/members-panel";
import { SlackPanel } from "@/components/settings/slack-panel";
import { VoiceFields } from "@/components/settings/voice-fields";
import { OnboardingSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  getAuthStatus,
  getComposio,
  getOrg,
  getSettings,
  getWorkspace,
  putSettings,
  setComposioKey,
} from "@/lib/api";
import {
  ONBOARDING_STEPS,
  STEP_META,
  nextOnboardingStep,
  onboardingPath,
  resolveOnboardingStep,
  type OnboardingStep,
} from "@/lib/onboarding";
import type { Org } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

function oauthQuery(): string {
  const params = new URLSearchParams(window.location.search);
  const next = new URLSearchParams();
  const connected = params.get("connected");
  const error = params.get("error") ?? params.get("error_description");
  if (connected) next.set("connected", connected);
  if (error) next.set("error", error);
  const text = next.toString();
  return text ? `?${text}` : "";
}

export function OnboardingGate() {
  const router = useRouter();

  useEffect(() => {
    const query = oauthQuery();
    void getAuthStatus()
      .then((status) => {
        if (status.state === "setup") {
          router.replace("/setup");
          return;
        }
        if (status.state === "login") {
          router.replace("/login?next=/onboarding");
          return;
        }
        if (query) {
          router.replace(`${onboardingPath("sources")}${query}`);
          return;
        }
        router.replace(onboardingPath("workspace"));
      })
      .catch(() => {
        router.replace("/setup");
      });
  }, [router]);

  return <OnboardingSkeleton />;
}

export function OnboardingFlow({ requested }: { requested: string }) {
  const router = useRouter();
  const resolved = resolveOnboardingStep(requested);
  const [org, setOrg] = useState<Org | null>(null);
  const [about, setAbout] = useState("");
  const [voice, setVoice] = useState("");
  const [llmUrl, setLlmUrl] = useState("https://openrouter.ai/api/v1");
  const [llmKey, setLlmKey] = useState("");
  const [llmSet, setLlmSet] = useState(false);
  const [composioKey, setComposioKeyField] = useState("");
  const [composioSet, setComposioSet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    let alive = true;
    void getAuthStatus()
      .then((status) => {
        if (!alive) return;
        if (status.state === "setup") {
          router.replace("/setup");
          return;
        }
        if (status.state === "login") {
          router.replace("/login?next=/onboarding");
          return;
        }
        return Promise.all([
            getOrg(),
            getSettings(),
            getWorkspace(),
            getComposio().catch(() => ({ configured: false })),
          ]).then(
          ([{ org: existing }, settings, workspace, composio]) => {
            if (!alive) return;
            const admin = Boolean(
              workspace.me.is_admin ||
                workspace.me.role === "admin" ||
                workspace.me.role === "owner",
            );
            if (!admin) {
              router.replace("/");
              return;
            }
            setLlmUrl(settings.llm_base_url || "https://openrouter.ai/api/v1");
            setLlmSet(settings.llm_api_key_set);
            setAbout(settings.workspace_about ?? "");
            setVoice(settings.voice ?? "");
            setComposioSet(Boolean(composio.configured));
            if (existing) setOrg(existing);
            const query = oauthQuery();
            if (query && requested !== "sources") {
              router.replace(`${onboardingPath("sources")}${query}`);
              return;
            }
            const mapped = resolveOnboardingStep(requested);
            if (mapped && mapped !== requested) {
              router.replace(`${onboardingPath(mapped)}${query}`);
              return;
            }
            if (!mapped) {
              router.replace(onboardingPath("workspace"));
              return;
            }
            setBooting(false);
          },
        );
      })
      .catch(() => {
        if (!alive) return;
        router.replace("/setup");
      });
    return () => {
      alive = false;
    };
  }, [requested, router]);

  const goNext = useCallback(
    (step: OnboardingStep) => {
      const next = nextOnboardingStep(step);
      if (next === "home") router.push("/");
      else router.push(onboardingPath(next));
    },
    [router],
  );

  const step = resolved;
  if (booting || !step) {
    return <OnboardingSkeleton />;
  }

  const stepIndex = ONBOARDING_STEPS.indexOf(step);
  const wide =
    step === "sources" || step === "people" || step === "mcp" || step === "slack";

  async function saveAndNext(
    stepNow: OnboardingStep,
    fn: () => Promise<void>,
  ) {
    setError(null);
    setBusy(true);
    try {
      await fn();
      goNext(stepNow);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`mx-auto flex min-h-full flex-col justify-center px-[var(--app-gutter)] py-16 ${
        wide ? "max-w-[var(--wide-max)]" : "max-w-[var(--page-max)]"
      }`}
    >
      <header className="mb-8 space-y-4">
        <BrandMark size={28} withWordmark />
        <p className="text-[12px] text-ink-3">
          Step {stepIndex + 1} of {ONBOARDING_STEPS.length} · {STEP_META[step]}
        </p>
      </header>

      {step === "workspace" && (
        <section className="space-y-5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">
            About {org?.name || "this company"}
          </h1>
          <p className="text-[13px] leading-relaxed text-ink-2">
            Optional. A short description in your words — not a website scrape.
            Name is already set from setup.
          </p>
          <Field label="About">
            <Textarea
              autoFocus
              value={about}
              placeholder="We build …"
              onChange={(e) => setAbout(e.target.value)}
            />
          </Field>
          {error && <p className="text-[12.5px] text-red">{error}</p>}
          <StepActions
            busy={busy}
            onContinue={() =>
              void saveAndNext("workspace", () =>
                putSettings({ workspace_about: about }),
              )
            }
            onSkip={() => router.push("/")}
          />
        </section>
      )}

      {step === "models" && (
        <section className="space-y-5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">
            Your LLM key
          </h1>
          <p className="text-[13px] leading-relaxed text-ink-2">
            {llmSet
              ? "A key is already saved. Continue, or paste a new one."
              : "Needed to talk. Skip and add one later from Settings → Models."}
          </p>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void saveAndNext("models", async () => {
                const key = llmKey.trim();
                await putSettings({
                  llm_base_url: llmUrl.trim(),
                  ...(key ? { llm_api_key: key } : {}),
                });
              });
            }}
          >
            <Field label="Base URL">
              <Input
                value={llmUrl}
                onChange={(e) => setLlmUrl(e.target.value)}
              />
            </Field>
            <Field label="API key">
              <Input
                autoFocus
                type="password"
                placeholder="sk-…"
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
              />
            </Field>
            {error && <p className="text-[12.5px] text-red">{error}</p>}
            <StepActions
              busy={busy}
              submit
              continueDisabled={!llmKey.trim() && !llmSet}
              onSkip={() => router.push("/")}
            />
          </form>
        </section>
      )}

      {step === "composio" && (
        <section className="space-y-5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">
            Composio API key
          </h1>
          <p className="text-[13px] leading-relaxed text-ink-2">
            The OAuth broker for Google, Notion, GitHub, and the rest. Create a
            key at{" "}
            <a
              href="https://dashboard.composio.dev"
              target="_blank"
              rel="noreferrer"
              className="text-accent-ink underline-offset-2 hover:underline"
            >
              dashboard.composio.dev
            </a>
            , paste it here, or set{" "}
            <code className="rounded-[4px] bg-field px-1 py-0.5 text-[12px]">
              COMPOSIO_API_KEY
            </code>{" "}
            in .env. joel does not ship a shared key.
            {composioSet ? " A key is already saved." : ""}
          </p>
          <Field label="Composio API key">
            <Input
              autoFocus
              type="password"
              placeholder="ak_…"
              value={composioKey}
              onChange={(e) => setComposioKeyField(e.target.value)}
            />
          </Field>
          {error && <p className="text-[12.5px] text-red">{error}</p>}
          <StepActions
            busy={busy}
            continueDisabled={!composioKey.trim() && !composioSet}
            onContinue={() =>
              void saveAndNext("composio", async () => {
                const trimmed = composioKey.trim();
                if (trimmed) await setComposioKey(trimmed);
              })
            }
            onSkip={() => router.push("/")}
          />
        </section>
      )}

      {step === "sources" && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-[15px] font-semibold tracking-tight text-ink">
                Sources
              </h1>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
                Indexed tools sync into memory. Live tools are for now-questions.
                Connect one at a time — Chat works with holes.
              </p>
            </div>
            <StepActions
              compact
              onContinue={() => goNext("sources")}
              onSkip={() => router.push("/")}
            />
          </div>
          <IntegrationsPanel surface="onboarding" />
        </section>
      )}

      {step === "slack" && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h1 className="text-[15px] font-semibold tracking-tight text-ink">
              Slack bot
            </h1>
            <StepActions
              compact
              onContinue={() => goNext("slack")}
              onSkip={() => router.push("/")}
            />
          </div>
          <SlackPanel />
        </section>
      )}

      {step === "people" && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h1 className="text-[15px] font-semibold tracking-tight text-ink">
              People
            </h1>
            <StepActions
              compact
              onContinue={() => goNext("people")}
              onSkip={() => router.push("/")}
            />
          </div>
          <MembersPanel />
        </section>
      )}

      {step === "mcp" && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-[15px] font-semibold tracking-tight text-ink">
                MCP
              </h1>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
                Mint a key, then paste the snippet into Cursor or Claude. One
                tool: ask.
              </p>
            </div>
            <StepActions
              compact
              onContinue={() => goNext("mcp")}
              onSkip={() => router.push("/")}
            />
          </div>
          <ApiKeysPanel />
        </section>
      )}

      {step === "voice" && (
        <section className="space-y-5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">
            How it talks
          </h1>
          <p className="text-[13px] leading-relaxed text-ink-2">
            Optional. Stored with the other settings and injected into the
            answer prompt. Change it later in Settings → General.
          </p>
          <VoiceFields value={voice} onChange={setVoice} />
          {error && <p className="text-[12.5px] text-red">{error}</p>}
          <StepActions
            busy={busy}
            continueLabel="Finish"
            onContinue={() =>
              void saveAndNext("voice", () => putSettings({ voice }))
            }
            onSkip={() => router.push("/")}
          />
        </section>
      )}
    </div>
  );
}

function StepActions({
  busy,
  submit,
  compact,
  continueDisabled,
  continueLabel = "Continue",
  onContinue,
  onSkip,
}: {
  busy?: boolean;
  submit?: boolean;
  compact?: boolean;
  continueDisabled?: boolean;
  continueLabel?: string;
  onContinue?: () => void;
  onSkip: () => void;
}) {
  return (
    <div className={`flex flex-wrap gap-2 ${compact ? "" : ""}`}>
      <Button
        type={submit ? "submit" : "button"}
        variant="accent"
        size={compact ? "sm" : "md"}
        loading={busy}
        disabled={continueDisabled}
        onClick={submit ? undefined : onContinue}
      >
        {continueLabel}
      </Button>
      <Button
        type="button"
        variant="secondary"
        size={compact ? "sm" : "md"}
        onClick={onSkip}
      >
        Skip for now
      </Button>
    </div>
  );
}
