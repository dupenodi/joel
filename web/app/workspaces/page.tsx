"use client";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { WorkspaceAvatar } from "@/components/settings/workspace-avatar";
import { Input } from "@/components/ui/input";
import {
  createWorkspace,
  getAuthStatus,
  listWorkspaces,
  logout,
  switchWorkspace,
} from "@/lib/api";
import { authDestination, slugPreview } from "@/lib/auth";
import type { WorkspaceMembership } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

export default function WorkspacesPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [workspaces, setWorkspaces] = useState<WorkspaceMembership[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getAuthStatus()
      .then((status) => {
        const dest = authDestination(status, "/workspaces");
        if (dest) {
          router.replace(dest);
          return;
        }
        const listed = status.workspaces ?? [];
        if (listed.length > 0) {
          setWorkspaces(listed);
          setChecking(false);
          return;
        }
        return listWorkspaces().then((res) => {
          setWorkspaces(res.workspaces);
          setChecking(false);
        });
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  if (checking) return <OnboardingSkeleton />;

  const slug = slugPreview(name);

  return (
    <AuthScreen kicker="Your workspaces" title="Choose a workspace">
      <ul className="space-y-2">
        {workspaces.map((ws) => (
          <li key={ws.id}>
            <button
              type="button"
              disabled={busyId !== null}
              onClick={() => {
                setError(null);
                setBusyId(ws.id);
                void switchWorkspace(ws.id)
                  .then(() => router.replace("/"))
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Could not switch workspace",
                    );
                    setBusyId(null);
                  });
              }}
              className="flex w-full items-center gap-3 rounded-card bg-surface p-3 text-left shadow-card transition-colors hover:bg-hover disabled:opacity-60"
            >
              <WorkspaceAvatar
                name={ws.name}
                logoUrl={ws.logo_url}
                size={40}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold text-ink">
                  {ws.name}
                </span>
                <span className="block truncate text-[12px] text-ink-3">
                  {ws.domain} · {ws.role}
                </span>
              </span>
              {busyId === ws.id && (
                <span className="text-[12px] text-ink-3">Opening…</span>
              )}
            </button>
          </li>
        ))}
      </ul>

      {error && <p className="mt-3 text-[12.5px] text-red">{error}</p>}

      {!showCreate ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="accent"
            onClick={() => setShowCreate(true)}
          >
            Create workspace
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => router.push("/join")}
          >
            Join workspace
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => {
              void logout().then(() => router.replace("/login"));
            }}
          >
            Sign out
          </Button>
        </div>
      ) : (
        <form
          className="mt-4 space-y-3 border-t border-line pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            setCreating(true);
            setError(null);
            void createWorkspace({
              name: name.trim(),
              domain: domain.trim() || undefined,
            })
              .then(() => router.replace("/"))
              .catch((err: unknown) => {
                setError(
                  err instanceof Error
                    ? err.message
                    : "Could not create workspace",
                );
              })
              .finally(() => setCreating(false));
          }}
        >
          <Field label="Company name">
            <Input
              autoFocus
              value={name}
              placeholder="Acme"
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field
            label="Domain"
            hint={slug ? `Workspace URL · ${slug}` : "Optional."}
          >
            <Input
              value={domain}
              placeholder="acme.dev"
              onChange={(e) => setDomain(e.target.value)}
            />
          </Field>
          <div className="flex gap-2">
            <Button
              type="submit"
              size="sm"
              variant="accent"
              loading={creating}
              disabled={!name.trim()}
            >
              Create
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </AuthScreen>
  );
}
