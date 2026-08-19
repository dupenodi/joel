"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { acceptInvite, peekInvite } from "@/lib/api";
import type { InvitePeek } from "@/lib/types";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

function JoinForm() {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token")?.trim() ?? "";
  const [peek, setPeek] = useState<InvitePeek | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setError("This invite link is missing a token.");
      setLoading(false);
      return;
    }
    void peekInvite(token)
      .then((data) => {
        setPeek(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Invite not found");
        setLoading(false);
      });
  }, [token]);

  if (loading) return <OnboardingSkeleton />;

  if (!peek) {
    return (
      <AuthScreen title="Invite not valid">
        <p className="text-[13px] leading-relaxed text-ink-2">{error}</p>
        <Button className="mt-4" variant="secondary" onClick={() => router.push("/login")}>
          Sign in
        </Button>
      </AuthScreen>
    );
  }

  return (
    <AuthScreen
      kicker={`${peek.workspace_name} · ${peek.workspace_domain}`}
      title="Join this workspace"
    >
      <p className="mb-4 text-[13px] leading-relaxed text-ink-2">
        Invited as <span className="text-ink">{peek.email}</span> ({peek.role}).
      </p>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setBusy(true);
          void acceptInvite(token, {
            password,
            display_name: displayName,
          })
            .then(() => router.replace("/"))
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not join");
            })
            .finally(() => setBusy(false));
        }}
      >
        <Field label="Your name">
          <Input
            autoFocus
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <p className="text-[12.5px] text-red">{error}</p>}
        <Button
          type="submit"
          variant="accent"
          loading={busy}
          disabled={password.length < 8}
        >
          Join
        </Button>
      </form>
    </AuthScreen>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={<OnboardingSkeleton />}>
      <JoinForm />
    </Suspense>
  );
}
