"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { OnboardingSkeleton } from "@/components/skeletons";
import {
  getAuthStatus,
  getMcpOAuthPending,
  submitMcpOAuthConsent,
} from "@/lib/api";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

function ConsentForm() {
  const router = useRouter();
  const search = useSearchParams();
  const rid = (search.get("rid") || "").trim();
  const here = rid
    ? `/oauth/consent?rid=${encodeURIComponent(rid)}`
    : "/oauth/consent";

  const [checking, setChecking] = useState(true);
  const [clientName, setClientName] = useState("MCP client");
  const [workspaceName, setWorkspaceName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"allow" | "deny" | null>(null);

  useEffect(() => {
    if (!rid) {
      setError("Missing sign-in request. Start again from Cursor.");
      setChecking(false);
      return;
    }
    let alive = true;
    void Promise.all([getAuthStatus(), getMcpOAuthPending(rid)])
      .then(([status, pending]) => {
        if (!alive) return;
        if (status.state === "setup") {
          router.replace("/setup");
          return;
        }
        if (status.state === "login") {
          router.replace(`/login?next=${encodeURIComponent(here)}`);
          return;
        }
        if (status.state === "pick_workspace") {
          router.replace(`/workspaces?next=${encodeURIComponent(here)}`);
          return;
        }
        setClientName(pending.client_name || "MCP client");
        setWorkspaceName(status.workspace?.name || "this workspace");
        setChecking(false);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(
          err instanceof Error
            ? err.message
            : "This sign-in request expired. Start again from Cursor.",
        );
        setChecking(false);
      });
    return () => {
      alive = false;
    };
  }, [here, rid, router]);

  if (checking) return <OnboardingSkeleton />;

  async function decide(allow: boolean) {
    setError(null);
    setBusy(allow ? "allow" : "deny");
    try {
      const { redirect } = await submitMcpOAuthConsent(rid, allow);
      window.location.assign(redirect);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not finish sign-in.",
      );
      setBusy(null);
    }
  }

  return (
    <AuthScreen kicker={workspaceName || "MCP"} title={`Allow ${clientName}?`}>
      <p className="text-[13.5px] leading-relaxed text-ink-2">
        {clientName} wants to ask this workspace&apos;s memory as you. Same
        visibility as Chat. One tool: ask.
      </p>
      {error && <p className="mt-3 text-[12.5px] text-red">{error}</p>}
      {rid ? (
        <div className="mt-5 flex flex-wrap gap-2">
          <Button
            type="button"
            variant="accent"
            loading={busy === "allow"}
            disabled={busy !== null}
            onClick={() => void decide(true)}
          >
            Allow
          </Button>
          <Button
            type="button"
            variant="secondary"
            loading={busy === "deny"}
            disabled={busy !== null}
            onClick={() => void decide(false)}
          >
            Deny
          </Button>
        </div>
      ) : null}
    </AuthScreen>
  );
}

export default function OAuthConsentPage() {
  return (
    <Suspense fallback={<OnboardingSkeleton />}>
      <ConsentForm />
    </Suspense>
  );
}
