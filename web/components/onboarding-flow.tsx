"use client";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { OrgCard } from "@/components/org-card";
import { OnboardingSkeleton } from "@/components/skeletons";
import { Input } from "@/components/ui/input";
import {
  getAuthStatus,
  getOrg,
  getSettings,
  putSettings,
} from "@/lib/api";
import type { Org } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

export const ONBOARDING_STEPS = ["llm", "tools"] as const;
export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

const STEP_META: Record<OnboardingStep, string> = {
  llm: "LLM",
  tools: "Tools",
};

export function isOnboardingStep(value: string | undefined): value is OnboardingStep {
  return value === "llm" || value === "tools";
}

export function inferOnboardingStep(input: {
  llmSet: boolean;
  ready: boolean;
}): OnboardingStep | "home" {
  if (input.ready) return "home";
  if (!input.llmSet) return "llm";
  return "tools";
}

export function onboardingPath(step: OnboardingStep): string {
  return `/onboarding/${step}`;
}

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
        return Promise.all([getOrg(), getSettings()]).then(
          ([{ checklist }, settings]) => {
            if (query) {
              router.replace(`${onboardingPath("tools")}${query}`);
              return;
            }
            const next = inferOnboardingStep({
              llmSet: settings.llm_api_key_set,
              ready: checklist.ready,
            });
            if (next === "home") {
              router.replace("/");
              return;
            }
            router.replace(onboardingPath(next));
          },
        );
      })
      .catch(() => {
        router.replace("/setup");
      });
  }, [router]);

  return <OnboardingSkeleton />;
}

export function OnboardingFlow({ requested }: { requested: string }) {
  const router = useRouter();
  const step = isOnboardingStep(requested) ? requested : null;
  const [org, setOrg] = useState<Org | null>(null);
  const [llmUrl, setLlmUrl] = useState("https://openrouter.ai/api/v1");
  const [llmKey, setLlmKey] = useState("");
  const [llmSet, setLlmSet] = useState(false);
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
        return Promise.all([getOrg(), getSettings()]).then(
          ([{ org: existing, checklist }, settings]) => {
            if (!alive) return;
            setLlmUrl(settings.llm_base_url || "https://openrouter.ai/api/v1");
            setLlmSet(settings.llm_api_key_set);
            if (existing) setOrg(existing);
            const inferred = inferOnboardingStep({
              llmSet: settings.llm_api_key_set,
              ready: checklist.ready,
            });
            if (inferred === "home") {
              router.replace("/");
              return;
            }
            const query = oauthQuery();
            if (query) {
              if (requested !== "tools") {
                router.replace(`${onboardingPath("tools")}${query}`);
                return;
              }
              setBooting(false);
              return;
            }
            if (!isOnboardingStep(requested)) {
              router.replace(onboardingPath(inferred));
              return;
            }
            if (requested === "tools" && !settings.llm_api_key_set) {
              router.replace(onboardingPath("llm"));
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

  const onSaveLlm = useCallback(async () => {
    const key = llmKey.trim();
    if (!key && !llmSet) return;
    setError(null);
    setBusy(true);
    try {
      await putSettings({
        llm_base_url: llmUrl.trim(),
        ...(key ? { llm_api_key: key } : {}),
      });
      setLlmSet(true);
      setLlmKey("");
      router.push(onboardingPath("tools"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save key");
    } finally {
      setBusy(false);
    }
  }, [llmKey, llmSet, llmUrl, router]);

  if (booting || !step) {
    return <OnboardingSkeleton />;
  }

  const stepIndex = ONBOARDING_STEPS.indexOf(step);

  return (
    <div
      className={`mx-auto flex min-h-full flex-col justify-center px-[var(--app-gutter)] py-16 ${
        step === "tools" ? "max-w-[var(--wide-max)]" : "max-w-[var(--page-max)]"
      }`}
    >
      <header className="mb-8 space-y-4">
        <BrandMark size={28} withWordmark />
        <p className="text-[12px] text-ink-3">
          Step {stepIndex + 1} of {ONBOARDING_STEPS.length} · {STEP_META[step]}
        </p>
      </header>

      {step === "llm" && (
        <section className="space-y-5">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">
            Your LLM key
          </h1>
          <p className="text-[13px] leading-relaxed text-ink-2">
            {llmSet
              ? "A key is already saved. Continue, or paste a new one."
              : "Paste a key, or skip and add one later from Settings → Models."}
          </p>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void onSaveLlm();
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
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                variant="accent"
                loading={busy}
                disabled={!llmKey.trim() && !llmSet}
              >
                Continue
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => router.push("/")}
              >
                Skip for now
              </Button>
            </div>
          </form>
        </section>
      )}

      {step === "tools" && org && (
        <section className="space-y-5">
          <OrgCard
            name={org.name}
            domain={org.domain}
            logoUrl={org.logo_url}
          />
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-[15px] font-semibold tracking-tight text-ink">
                Connect tools
              </h1>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
                One at a time. After you connect, pulling continues here in the
                background.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => router.push("/")}
            >
              Continue
            </Button>
          </div>
          <IntegrationsPanel surface="onboarding" />
        </section>
        )}
    </div>
  );
}
