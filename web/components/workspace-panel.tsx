"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import {
  createInvite,
  getWorkspace,
  logout,
  patchWorkspace,
  removeMember,
  revokeInvite,
  setMemberRole,
} from "@/lib/api";
import type { Me, Workspace, WorkspaceInvite, WorkspaceMember } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

function inviteUrl(token: string): string {
  return `${window.location.origin}/join?token=${encodeURIComponent(token)}`;
}

export function WorkspacePanel() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invites, setInvites] = useState<WorkspaceInvite[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freshLink, setFreshLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const reload = useCallback(async () => {
    const data = await getWorkspace();
    setWorkspace(data.workspace);
    setMe(data.me);
    setMembers(data.members);
    setInvites(data.invites);
    setName(data.workspace.name);
  }, []);

  useEffect(() => {
    void reload().catch(() => {});
  }, [reload]);

  if (!workspace || !me) return null;

  const admin = me.role === "admin";

  return (
    <section className="space-y-3">
      <h2 className="text-[11px] font-medium tracking-[0.04em] text-ink-3 uppercase">
        Workspace
      </h2>
      <p className="text-[13px] leading-relaxed text-ink-2">
        {workspace.domain} · {members.length}{" "}
        {members.length === 1 ? "person" : "people"}.
      </p>

      {admin && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Name" className="min-w-48 flex-1">
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
            />
          </Field>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            loading={busy}
            onClick={() => {
              setBusy(true);
              setError(null);
              void patchWorkspace({ name })
                .then((res) => setWorkspace(res.workspace))
                .catch((err: unknown) => {
                  setError(err instanceof Error ? err.message : "Could not save");
                })
                .finally(() => setBusy(false));
            }}
          >
            Save
          </Button>
        </div>
      )}

      <ul className="divide-y divide-line rounded-card bg-surface shadow-card">
        {members.map((member) => (
          <li
            key={member.id}
            className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-ink">
                {member.display_name}
                {member.id === me.id ? (
                  <span className="ml-1.5 font-normal text-ink-3">you</span>
                ) : null}
              </p>
              <p className="truncate text-[12px] text-ink-3">{member.email}</p>
            </div>
            {admin && member.id !== me.id ? (
              <div className="flex items-center gap-2">
                <select
                  aria-label={`Role for ${member.display_name}`}
                  className="h-8 rounded-control bg-field px-2 text-[13px] text-ink shadow-hairline"
                  value={member.role}
                  onChange={(e) => {
                    const next = e.target.value as "admin" | "member";
                    void setMemberRole(member.id, next)
                      .then(() => reload())
                      .catch((err: unknown) => {
                        setError(err instanceof Error ? err.message : "Could not change role");
                      });
                  }}
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    void removeMember(member.id)
                      .then(() => reload())
                      .catch((err: unknown) => {
                        setError(err instanceof Error ? err.message : "Could not remove");
                      });
                  }}
                >
                  Remove
                </Button>
              </div>
            ) : (
              <p className="text-[12px] capitalize text-ink-3">{member.role}</p>
            )}
          </li>
        ))}
      </ul>

      {admin && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            setCopied(false);
            void createInvite({ email, role })
              .then((res) => {
                setInvites(res.invites);
                setFreshLink(inviteUrl(res.token));
                setEmail("");
              })
              .catch((err: unknown) => {
                setError(err instanceof Error ? err.message : "Could not invite");
              })
              .finally(() => setBusy(false));
          }}
        >
          <p className="text-[13px] text-ink-2">
            Invite with a link. No email is sent from this machine.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Email" className="min-w-48 flex-1">
              <Input
                type="email"
                value={email}
                placeholder="teammate@yourco.dev"
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <select
              aria-label="Invite role"
              className="h-9 rounded-control bg-field px-2 text-[13px] text-ink shadow-hairline"
              value={role}
              onChange={(e) => setRole(e.target.value as "admin" | "member")}
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <Button
              type="submit"
              size="sm"
              variant="accent"
              loading={busy}
              disabled={!email.trim()}
            >
              Invite
            </Button>
          </div>
        </form>
      )}

      {freshLink && (
        <div className="rounded-card bg-field p-3">
          <p className="text-[12px] text-ink-3">Give them this link once.</p>
          <p className="mt-1 break-all text-[12.5px] text-ink">{freshLink}</p>
          <Button
            className="mt-2"
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(freshLink).then(() => setCopied(true));
            }}
          >
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      )}

      {admin && invites.length > 0 && (
        <ul className="space-y-1.5">
          {invites.map((invite) => (
            <li
              key={invite.id}
              className="flex items-center justify-between gap-2 text-[12.5px] text-ink-2"
            >
              <span>
                {invite.email} · {invite.role}
              </span>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  void revokeInvite(invite.id)
                    .then(() => reload())
                    .catch((err: unknown) => {
                      setError(err instanceof Error ? err.message : "Could not revoke");
                    });
                }}
              >
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-[13px] text-red">{error}</p>}

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
    </section>
  );
}
