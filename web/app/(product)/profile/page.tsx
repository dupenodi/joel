"use client";

import { Field } from "@/components/field";
import { OrgCard } from "@/components/org-card";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { Surface } from "@/components/surface";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getProfile, putProfile, wipeOrg } from "@/lib/api";
import type { Profile } from "@/lib/types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function ProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined);
  const [name, setName] = useState("");
  const [wipeConfirm, setWipeConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p);
        if (p) setName(p.display_name);
      })
      .catch(() => setProfile(null));
  }, []);

  if (profile === undefined) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-10 text-sm text-muted">
        Loading…
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto max-w-md px-6 py-16 text-center">
        <h1 className="font-display text-2xl font-semibold">No org yet</h1>
        <p className="mt-2 text-ink-soft">Finish onboarding first.</p>
        <Link
          href="/onboarding"
          className="mt-6 inline-block text-sm underline underline-offset-2"
        >
          Start onboarding
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-10 px-6 py-10">
      <header className="flex items-center gap-4">
        <Avatar name={name || profile.display_name} size={56} />
        <div className="min-w-0 flex-1">
          <PageHeader
            className="mb-0"
            title={name || profile.display_name}
            description="Single-user install · no login"
          />
        </div>
      </header>

      <section className="space-y-3">
        <Field label="Display name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={async () => {
            setError(null);
            try {
              await putProfile(name);
              setMsg("Profile saved");
              const p = await getProfile();
              setProfile(p);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Save failed");
            }
          }}
        >
          Save name
        </Button>
        {msg && <p className="text-sm text-[var(--ok)]">{msg}</p>}
        {error && <p className="text-sm text-accent">{error}</p>}
      </section>

      <OrgCard
        name={profile.org.name}
        domain={profile.org.domain}
        logoUrl={profile.org.logo_url}
      />

      <section>
        <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.06em] text-muted">
          Corpus
        </h2>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Docs" value={profile.corpus.docs} />
          <Stat label="Artifacts" value={profile.corpus.artifacts} />
          <Stat label="Entities" value={profile.corpus.entities} />
          <Stat
            label="Index"
            value={profile.corpus.index.consistent ? "consistent" : "drift"}
          />
        </dl>
        <p className="mt-3 text-xs text-muted">
          SQLite {profile.corpus.index.sqlite} · vectors{" "}
          {profile.corpus.index.vectors} · graph {profile.corpus.index.graph}
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.06em] text-muted">
          Spend (30d LLM calls)
        </h2>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {Object.entries(profile.spend_30d).map(([stage, n]) => (
            <Stat key={stage} label={stage} value={n} />
          ))}
        </dl>
      </section>

      <Surface className="border-accent/30 bg-[var(--accent-soft)]">
        <h2 className="font-medium text-accent">Danger zone</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Wipe org truncates SQLite state. Type{" "}
          <strong>{profile.org.domain}</strong> to confirm.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Field label="Confirm domain" className="max-w-xs flex-1">
            <Input
              className="bg-surface"
              value={wipeConfirm}
              onChange={(e) => setWipeConfirm(e.target.value)}
              placeholder={profile.org.domain}
            />
          </Field>
          <div className="flex items-end">
            <Button
              type="button"
              variant="danger"
              disabled={wipeConfirm !== profile.org.domain}
              onClick={async () => {
                await wipeOrg(profile.org.domain);
                router.push("/onboarding");
              }}
            >
              Wipe org
            </Button>
          </div>
        </div>
      </Surface>
    </div>
  );
}
