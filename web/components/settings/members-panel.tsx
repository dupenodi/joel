"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { CopyButton } from "@/components/beautifului/primitives/copy-button";
import { Field } from "@/components/field";
import {
  PersonAvatar,
} from "@/components/settings/workspace-avatar";
import {
  SettingsEmpty,
  SettingsSection,
} from "@/components/settings/settings-section";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  createInvite,
  getWorkspace,
  removeMember,
  resendInvite,
  revokeInvite,
  setMemberRole,
} from "@/lib/api";
import type { Me, WorkspaceInvite, WorkspaceMember } from "@/lib/types";
import { useCallback, useEffect, useState } from "react";

const SELECT_CLASS =
  "h-9 rounded-control bg-field px-2.5 text-[14px] text-ink shadow-hairline outline-none transition-colors duration-150 hover:bg-hover focus:bg-surface focus:shadow-btn";

function inviteUrl(token: string): string {
  return `${window.location.origin}/join?token=${encodeURIComponent(token)}`;
}

/** Split on commas, whitespace, or newlines; drop empties; de-dupe case-insensitively. */
function parseInviteEmails(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of raw.split(/[\s,;]+/)) {
    const email = part.trim();
    if (!email) continue;
    const key = email.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(email);
  }
  return out;
}

type FreshInvite = {
  email: string;
  url: string;
  emailSent: boolean;
  emailError: string | null;
};

export function MembersPanel() {
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invites, setInvites] = useState<WorkspaceInvite[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [emails, setEmails] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [busy, setBusy] = useState(false);
  const [freshInvites, setFreshInvites] = useState<FreshInvite[]>([]);
  const [mailConfigured, setMailConfigured] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);

  const reload = useCallback(async () => {
    const data = await getWorkspace();
    setMe(data.me);
    setMembers(data.members);
    setInvites(data.invites);
  }, []);

  useEffect(() => {
    void reload().catch(() => {});
  }, [reload]);

  if (!me) return null;

  const admin = me.is_admin || me.role === "admin" || me.role === "owner";
  const canAssignOwner = Boolean(me.is_owner || me.role === "owner");
  const parsedEmails = parseInviteEmails(emails);

  function closeInvite() {
    setInviteOpen(false);
    setEmails("");
    setRole("member");
    setError(null);
  }

  return (
    <div className="space-y-6">
      <SettingsSection
        title="Members"
        description={
          admin
            ? "People with access to this workspace. Invite one or many — email when configured, otherwise share the links."
            : "People with access to this workspace."
        }
        headerAside={
          admin ? (
            <Button
              type="button"
              size="sm"
              variant="accent"
              onClick={() => setInviteOpen(true)}
            >
              Invite members
            </Button>
          ) : undefined
        }
      >
        <ul className="-mx-5 divide-y divide-line border-t border-line">
          {members.map((member) => (
            <li
              key={member.id}
              className="flex flex-wrap items-center justify-between gap-2 px-5 py-3"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <PersonAvatar name={member.display_name} />
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 truncate text-[13.5px] font-medium text-ink">
                    <span className="truncate">{member.display_name}</span>
                    {member.id === me.id && (
                      <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-accent-tint px-1.5 text-[10.5px] font-medium text-ink">
                        you
                      </span>
                    )}
                  </p>
                  <p className="truncate text-[12px] text-ink-3">{member.email}</p>
                </div>
              </div>
              {admin && member.id !== me.id && !(member.role === "owner" && !canAssignOwner) ? (
                <div className="flex items-center gap-2">
                  <select
                    aria-label={`Role for ${member.display_name}`}
                    className={SELECT_CLASS}
                    value={member.role}
                    onChange={(e) => {
                      const next = e.target.value as "owner" | "admin" | "member";
                      void setMemberRole(member.id, next)
                        .then(() => reload())
                        .catch((err: unknown) => {
                          setError(
                            err instanceof Error
                              ? err.message
                              : "Could not change role",
                          );
                        });
                    }}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                    {canAssignOwner ? (
                      <option value="owner">Owner</option>
                    ) : null}
                  </select>
                  <Button
                    type="button"
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      void removeMember(member.id)
                        .then(() => reload())
                        .catch((err: unknown) => {
                          setError(
                            err instanceof Error
                              ? err.message
                              : "Could not remove",
                          );
                        });
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <span className="inline-flex h-5.5 shrink-0 items-center rounded-full bg-field px-2 text-[11.5px] font-medium capitalize text-ink-2">
                  {member.role}
                </span>
              )}
            </li>
          ))}
        </ul>
        {error && !inviteOpen && (
          <p className="mt-3 text-[13px] text-red">{error}</p>
        )}
      </SettingsSection>

      {admin && (
        <SettingsSection
          title="Pending invites"
          description="Resend rotates the link and re-emails when mail is configured. Revoke any you no longer want used."
        >
          {invites.length === 0 ? (
            <SettingsEmpty>No pending invites.</SettingsEmpty>
          ) : (
            <ul className="divide-y divide-line rounded-card border border-line">
              {invites.map((invite) => (
                <li
                  key={invite.id}
                  className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-[13px]"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{invite.email}</p>
                    <p className="text-[12px] capitalize text-ink-3">
                      {invite.role}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setError(null);
                        void resendInvite(invite.id)
                          .then((res) => {
                            setInvites(res.invites);
                            setMailConfigured(res.mail_configured);
                            setFreshInvites([
                              {
                                email: res.email,
                                url: inviteUrl(res.token),
                                emailSent: res.email_sent,
                                emailError: res.email_error,
                              },
                            ]);
                            setLinkOpen(true);
                          })
                          .catch((err: unknown) => {
                            setError(
                              err instanceof Error
                                ? err.message
                                : "Could not resend",
                            );
                          });
                      }}
                    >
                      Resend
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        void revokeInvite(invite.id)
                          .then(() => reload())
                          .catch((err: unknown) => {
                            setError(
                              err instanceof Error
                                ? err.message
                                : "Could not revoke",
                            );
                          });
                      }}
                    >
                      Revoke
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SettingsSection>
      )}

      <Dialog
        open={inviteOpen}
        onClose={closeInvite}
        title="Invite members"
      >
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">Invite members</h2>
          <p className="mt-1 text-[13px] text-ink-2">
            Separate emails with commas. Each person gets their own invite
            link — emailed when outbound mail is configured.
          </p>
        </div>
        <form
          className="space-y-3 px-5 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            const list = parseInviteEmails(emails);
            if (list.length === 0) return;
            setBusy(true);
            setError(null);
            void (async () => {
              const created: FreshInvite[] = [];
              const failures: string[] = [];
              let lastInvites = invites;
              let mailOn = false;
              for (const email of list) {
                try {
                  const res = await createInvite({ email, role });
                  lastInvites = res.invites;
                  mailOn = res.mail_configured;
                  created.push({
                    email: res.email || email,
                    url: inviteUrl(res.token),
                    emailSent: res.email_sent,
                    emailError: res.email_error,
                  });
                } catch (err: unknown) {
                  failures.push(
                    `${email}: ${
                      err instanceof Error ? err.message : "Could not invite"
                    }`,
                  );
                }
              }
              setInvites(lastInvites);
              setMailConfigured(mailOn);
              setBusy(false);
              if (created.length > 0) {
                setFreshInvites(created);
                setInviteOpen(false);
                setEmails("");
                setRole("member");
                setLinkOpen(true);
                if (failures.length > 0) {
                  setError(failures.join(" · "));
                }
              } else {
                setError(
                  failures.join(" · ") || "Could not create any invites",
                );
              }
            })();
          }}
        >
          <Field
            label="Emails"
            hint={
              parsedEmails.length > 1
                ? `${parsedEmails.length} people`
                : undefined
            }
          >
            <Input
              autoFocus
              value={emails}
              placeholder="alice@yourco.dev, bob@yourco.dev"
              onChange={(e) => setEmails(e.target.value)}
            />
          </Field>
          <Field label="Role">
            <select
              aria-label="Invite role"
              className={`${SELECT_CLASS} w-full`}
              value={role}
              onChange={(e) =>
                setRole(e.target.value as "admin" | "member")
              }
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          {error && <p className="text-[13px] text-red">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" size="sm" variant="secondary" onClick={closeInvite}>
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              variant="accent"
              loading={busy}
              disabled={parsedEmails.length === 0}
            >
              {parsedEmails.length > 1
                ? `Create ${parsedEmails.length} invites`
                : "Create invite"}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={linkOpen && freshInvites.length > 0}
        onClose={() => {
          setLinkOpen(false);
          setFreshInvites([]);
          setError(null);
        }}
        title="Invite links"
      >
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">
            {mailConfigured
              ? "Links (also emailed when send succeeded)"
              : "Give them these links"}
          </h2>
          <p className="mt-1 text-[13px] text-ink-2">
            Each link is shown once here. Copy before you close.
            {mailConfigured
              ? " Configure Email in settings if sends are failing."
              : ""}
          </p>
        </div>
        <div className="space-y-3 px-5 py-4">
          {error && <p className="text-[13px] text-red">{error}</p>}
          <ul className="max-h-72 space-y-3 overflow-y-auto">
            {freshInvites.map((item) => (
              <li
                key={item.email}
                className="rounded-control bg-field px-3 py-2.5"
              >
                <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {item.email}
                  </p>
                  <span className="text-[11.5px] text-ink-3">
                    {item.emailSent
                      ? "Email sent"
                      : item.emailError
                        ? `Email failed: ${item.emailError}`
                        : mailConfigured
                          ? "Email not sent"
                          : "Link only"}
                  </span>
                </div>
                <code className="block break-all text-[12px] text-ink-2">
                  {item.url}
                </code>
                <div className="mt-2 flex justify-end">
                  <CopyButton text={item.url} />
                </div>
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            {freshInvites.length > 1 && (
              <CopyButton
                variant="primary"
                label="Copy all"
                copiedLabel="Copied all"
                text={() =>
                  freshInvites
                    .map((item) => `${item.email}\n${item.url}`)
                    .join("\n\n")
                }
              />
            )}
            <Button
              type="button"
              size="sm"
              variant="accent"
              onClick={() => {
                setLinkOpen(false);
                setFreshInvites([]);
                setError(null);
              }}
            >
              Done
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
