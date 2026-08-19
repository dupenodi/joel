"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { getAuthStatus, login } from "@/lib/api";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/";
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState<string | null>(null);

  useEffect(() => {
    void getAuthStatus()
      .then((status) => {
        if (status.state === "setup") {
          router.replace("/setup");
          return;
        }
        if (status.state === "ok") {
          router.replace(next.startsWith("/") ? next : "/");
          return;
        }
        setWorkspaceName(status.workspace?.name ?? null);
        setChecking(false);
      })
      .catch(() => setChecking(false));
  }, [next, router]);

  if (checking) return <OnboardingSkeleton />;

  return (
    <AuthScreen
      kicker={workspaceName ? workspaceName : "Invite-only."}
      title="Sign in"
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setBusy(true);
          void login(email, password)
            .then(() => router.replace(next.startsWith("/") ? next : "/"))
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not sign in");
            })
            .finally(() => setBusy(false));
        }}
      >
        <Field label="Email">
          <Input
            autoFocus
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <p className="text-[12.5px] text-red">{error}</p>}
        <Button
          type="submit"
          variant="accent"
          loading={busy}
          disabled={!email.trim() || !password}
        >
          Continue
        </Button>
        <p className="text-[12.5px] text-ink-3">
          Need an account? Ask an admin for an invite link.
        </p>
      </form>
    </AuthScreen>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<OnboardingSkeleton />}>
      <LoginForm />
    </Suspense>
  );
}
