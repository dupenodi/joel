"use client";

import { BrandMark } from "@/components/brand-mark";
import { Checklist } from "@/components/checklist";
import { Field } from "@/components/field";
import { OrgCard } from "@/components/org-card";
import { StatusPill } from "@/components/status-pill";
import { StepIndicator } from "@/components/step-indicator";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { connectProvider, createOrg, getOrg } from "@/lib/api";
import { PROVIDER_META, SHIPPED_PROVIDERS } from "@/lib/connectors";
import type { Org, ReadinessChecklist } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

type Step = 1 | 2 | 3;

const CHECK_ITEMS: {
  key: keyof Omit<ReadinessChecklist, "ready">;
  label: string;
}[] = [
  { key: "fetched", label: "fetched" },
  { key: "distilled", label: "distilled" },
  { key: "people_resolved", label: "people resolved" },
  { key: "graph_linked", label: "graph linked" },
  { key: "indexes_consistent", label: "indexes consistent" },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [domain, setDomain] = useState("");
  const [org, setOrg] = useState<Org | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<ReadinessChecklist | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOrg()
      .then(({ org: existing, checklist: c }) => {
        if (!existing) return;
        setOrg(existing);
        setDomain(existing.domain);
        if (c.ready) {
          router.replace("/chat");
          return;
        }
        const started =
          c.fetched || c.distilled || c.people_resolved || c.graph_linked;
        if (started) {
          setStep(3);
          setChecklist(c);
        } else {
          setStep(2);
        }
      })
      .catch(() => {
        /* API down — stay on step 1 */
      });
  }, [router]);

  useEffect(() => {
    if (step !== 3) return;
    const id = setInterval(async () => {
      try {
        const { checklist: c } = await getOrg();
        setChecklist(c);
        if (c.ready) {
          clearInterval(id);
          setTimeout(() => router.push("/chat"), 600);
        }
      } catch {
        /* ignore */
      }
    }, 900);
    return () => clearInterval(id);
  }, [step, router]);

  const onCreateOrg = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const created = await createOrg(domain);
      setOrg(created);
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create org");
    } finally {
      setBusy(false);
    }
  }, [domain]);

  const onConnect = useCallback(async (p: string) => {
    setError(null);
    setBusy(true);
    setProvider(p);
    try {
      await connectProvider(p, "composio");
      setStep(3);
      setChecklist({
        fetched: false,
        distilled: false,
        people_resolved: false,
        graph_linked: false,
        indexes_consistent: false,
        ready: false,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed");
      setProvider(null);
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col justify-center px-6 py-16">
      <header className="mb-10 space-y-6">
        <BrandMark size={44} withWordmark />
        <StepIndicator
          step={step}
          total={3}
          label={`Step ${step} of 3 — ${
            step === 1 ? "your company" : step === 2 ? "first tool" : "first sync"
          }`}
        />
      </header>

      {step === 1 && (
        <section className="space-y-6">
          <div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              What’s your company domain?
            </h1>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
              joel is worthless without your data. Start with the domain.
            </p>
          </div>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void onCreateOrg();
            }}
          >
            <Field label="Domain">
              <Input
                autoFocus
                placeholder="yourco.dev"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
            </Field>
            {error && <p className="text-sm text-accent">{error}</p>}
            <Button type="submit" disabled={busy || !domain.trim()}>
              Continue
              <ArrowRight size={16} />
            </Button>
          </form>
        </section>
      )}

      {step === 2 && org && (
        <section className="space-y-6">
          <OrgCard
            name={org.name}
            domain={org.domain}
            logoUrl={org.logo_url}
          />
          <div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Connect your first tool
            </h1>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
              Slack, GitHub, or Gmail. No empty demo — memory starts with real
              data (or an empty ready gate for now).
            </p>
          </div>
          <div className="grid gap-3">
            {SHIPPED_PROVIDERS.map((p) => {
              const meta = PROVIDER_META[p];
              return (
                <button
                  key={p}
                  type="button"
                  disabled={busy}
                  onClick={() => void onConnect(p)}
                  className={cn(
                    "flex items-start gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-surface p-4 text-left shadow-[var(--shadow-sm)] transition-colors hover:border-[var(--line-strong)] disabled:opacity-60",
                    provider === p && "border-ink",
                  )}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={meta.icon}
                    alt=""
                    width={28}
                    height={28}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium">{meta.label}</p>
                      <StatusPill status="pending_auth" />
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                      {meta.blurb}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
          {error && <p className="text-sm text-accent">{error}</p>}
        </section>
      )}

      {step === 3 && checklist && (
        <section className="space-y-6">
          <div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Building memory
            </h1>
            <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
              First connector only. Chat opens when this checklist completes.
            </p>
          </div>
          <Surface elevation="hard">
            <Checklist
              items={CHECK_ITEMS.map(({ key, label }) => ({
                key,
                label,
                done: checklist[key],
              }))}
            />
          </Surface>
          {checklist.ready && (
            <p className="text-sm text-[var(--ok)]">Ready — opening chat…</p>
          )}
        </section>
      )}
    </div>
  );
}
