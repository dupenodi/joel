"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { getAuthStatus, setupWorkspace } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

export default function SetupPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [domain, setDomain] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasWorkspace, setHasWorkspace] = useState(false);

  useEffect(() => {
    void getAuthStatus()
      .then((status) => {
        if (status.state === "ok") {
          router.replace("/");
          return;
        }
        if (status.state === "login") {
          router.replace("/login");
          return;
        }
        if (status.workspace) {
          setDomain(status.workspace.domain);
          setHasWorkspace(true);
        }
        setChecking(false);
      })
      .catch(() => setChecking(false));
  }, [router]);

  if (checking) return <OnboardingSkeleton />;

  return (
    <AuthScreen
      kicker="First person here becomes admin."
      title={hasWorkspace ? "Create the admin account" : "Create this workspace"}
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setBusy(true);
          void setupWorkspace({
            email,
            password,
            display_name: displayName,
            domain: hasWorkspace ? undefined : domain,
          })
            .then(() => router.replace("/onboarding/llm"))
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not create workspace");
            })
            .finally(() => setBusy(false));
        }}
      >
        {!hasWorkspace && (
          <Field label="Company domain">
            <Input
              autoFocus
              placeholder="yourco.dev"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
          </Field>
        )}
        <Field label="Your name">
          <Input
            placeholder="Ada"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </Field>
        <Field label="Email">
          <Input
            type="email"
            autoComplete="email"
            placeholder="you@yourco.dev"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password" hint="At least 8 characters. Stored only on this machine.">
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
          disabled={!email.trim() || password.length < 8 || (!hasWorkspace && !domain.trim())}
        >
          Continue
        </Button>
      </form>
    </AuthScreen>
  );
}
