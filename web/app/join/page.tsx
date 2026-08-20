"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { acceptInvite, logout, peekInvite } from "@/lib/api";
import type { InvitePeek } from "@/lib/types";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

function tokenFromText(raw: string): string {
  const trimmed = raw.trim();
  try {
    const url = new URL(trimmed);
    return url.searchParams.get("token")?.trim() || trimmed;
  } catch {
    return trimmed;
  }
}

function JoinForm() {
  const router = useRouter();
  const search = useSearchParams();
  const tokenParam = search.get("token")?.trim() ?? "";
  const [pasted, setPasted] = useState("");
  const token = tokenParam || tokenFromText(pasted);
  const [peek, setPeek] = useState<InvitePeek | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(Boolean(tokenParam));

  useEffect(() => {
    if (!tokenParam) {
      setLoading(false);
      return;
    }
    void peekInvite(tokenParam)
      .then((data) => {
        setPeek(data);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Invite not found");
        setPeek(null);
        setLoading(false);
      });
  }, [tokenParam]);

  if (loading) return <OnboardingSkeleton />;

  if (!tokenParam && !peek) {
    return (
      <AuthScreen title="Join a workspace">
        <p className="mb-4 text-[13px] leading-relaxed text-ink-2">
          Paste the invite link you were sent.
        </p>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const next = tokenFromText(pasted);
            if (!next) return;
            router.replace(`/join?token=${encodeURIComponent(next)}`);
          }}
        >
          <Field label="Invite link">
            <Input
              autoFocus
              placeholder="https://…/join?token=…"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="accent" disabled={!tokenFromText(pasted)}>
            Continue
          </Button>
        </form>
      </AuthScreen>
    );
  }

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

  const joinPath = `/join?token=${encodeURIComponent(token)}`;
  const existing = Boolean(peek.account_exists);
  const viewer = peek.viewer ?? "anonymous";

  if (viewer === "other") {
    return (
      <AuthScreen
        title="Wrong account"
        workspace={{
          name: peek.workspace_name,
          domain: peek.workspace_domain,
          logoUrl: peek.workspace_logo_url,
        }}
      >
        <p className="text-[13px] leading-relaxed text-ink-2">
          This invite is for <span className="text-ink">{peek.email}</span>. Sign
          out, then open the link again.
        </p>
        <Button
          className="mt-4"
          variant="accent"
          onClick={() => {
            void logout().then(() => router.replace(joinPath));
          }}
        >
          Sign out
        </Button>
      </AuthScreen>
    );
  }

  const needPassword = viewer !== "invitee";
  const isNew = !existing;

  return (
    <AuthScreen
      title="Join this workspace"
      workspace={{
        name: peek.workspace_name,
        domain: peek.workspace_domain,
        logoUrl: peek.workspace_logo_url,
      }}
    >
      <p className="mb-4 text-[13px] leading-relaxed text-ink-2">
        Invited as <span className="text-ink">{peek.email}</span> ({peek.role}).
      </p>
      {existing && viewer === "anonymous" && (
        <p className="mb-4 text-[13px] leading-relaxed text-ink-2">
          You already have an account. Enter your password, or{" "}
          <button
            type="button"
            className="font-medium text-ink underline-offset-2 hover:underline"
            onClick={() =>
              router.push(`/login?next=${encodeURIComponent(joinPath)}`)
            }
          >
            sign in
          </button>
          .
        </p>
      )}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setBusy(true);
          void acceptInvite(token, {
            display_name: displayName,
            password: needPassword ? password : undefined,
          })
            .then(() => router.replace("/"))
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not join");
            })
            .finally(() => setBusy(false));
        }}
      >
        {isNew && (
          <Field label="Your name">
            <Input
              autoFocus
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </Field>
        )}
        {needPassword && (
          <Field
            label="Password"
            hint={
              isNew
                ? "At least 8 characters."
                : "Your current password — it will not be changed."
            }
          >
            <Input
              type="password"
              autoComplete={isNew ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}
        {error && <p className="text-[12.5px] text-red">{error}</p>}
        <Button
          type="submit"
          variant="accent"
          loading={busy}
          disabled={needPassword && (isNew ? password.length < 8 : !password)}
        >
          Join {peek.workspace_name}
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
