/** Browser client for joel-api (§12.2). */

import type {
  ApiKey,
  AuthStatus,
  ConnectorCard,
  Conversation,
  Health,
  InvitePeek,
  JobRow,
  Me,
  Message,
  Org,
  Profile,
  ReadinessChecklist,
  Settings,
  ComposioStatus,
  Workspace,
  WorkspaceInvite,
  WorkspaceMember,
  GraphSlice,
} from "./types";

const API = process.env.NEXT_PUBLIC_API ?? "";

function apiMessage(text: string, fallback: string): string {
  const trimmed = text.trim();
  if (!trimmed) return fallback;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (Array.isArray(parsed.detail) && parsed.detail[0]) {
      const first = parsed.detail[0] as { msg?: string };
      if (typeof first.msg === "string" && first.msg.trim()) {
        return first.msg.trim();
      }
    }
  } catch {
    /* not JSON */
  }
  return trimmed;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(apiMessage(text, `${res.status} ${res.statusText}`));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type OrgResponse = {
  org: Org | null;
  checklist: ReadinessChecklist;
  first_connector_id: string | null;
};

export async function getOrg(): Promise<OrgResponse> {
  return api("/api/org");
}

export async function getAuthStatus(): Promise<AuthStatus> {
  return api("/api/auth/status");
}

export async function listWorkspaces(): Promise<{
  workspaces: import("./types").WorkspaceMembership[];
}> {
  return api("/api/workspaces");
}

export async function switchWorkspace(orgId: number): Promise<AuthStatus> {
  return api("/api/auth/workspace", {
    method: "POST",
    body: JSON.stringify({ org_id: orgId }),
  });
}

export async function createWorkspace(input: {
  name?: string;
  domain?: string;
  slug?: string;
}): Promise<AuthStatus> {
  return api("/api/workspaces", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function setupWorkspace(input: {
  email: string;
  password: string;
  display_name?: string;
  domain?: string;
  name?: string;
}): Promise<AuthStatus> {
  return api("/api/auth/setup", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function login(email: string, password: string): Promise<AuthStatus> {
  return api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await api("/api/auth/logout", { method: "POST" });
}

export async function peekInvite(token: string): Promise<InvitePeek> {
  return api(`/api/auth/invite/${encodeURIComponent(token)}`);
}

export async function acceptInvite(
  token: string,
  input: { password?: string; display_name?: string } = {},
): Promise<AuthStatus> {
  return api(`/api/auth/invite/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getWorkspace(): Promise<{
  workspace: Workspace;
  me: Me;
  members: WorkspaceMember[];
  invites: WorkspaceInvite[];
}> {
  return api("/api/workspace");
}

export async function patchWorkspace(body: {
  domain?: string;
  name?: string;
}): Promise<{ workspace: Workspace }> {
  return api("/api/workspace", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function createInvite(input: {
  email: string;
  role: "admin" | "member";
}): Promise<{
  invite_id: string;
  token: string;
  email: string;
  invites: WorkspaceInvite[];
  email_sent: boolean;
  email_error: string | null;
  mail_configured: boolean;
}> {
  return api("/api/workspace/invites", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function resendInvite(inviteId: string): Promise<{
  invite_id: string;
  token: string;
  email: string;
  invites: WorkspaceInvite[];
  email_sent: boolean;
  email_error: string | null;
  mail_configured: boolean;
}> {
  return api(`/api/workspace/invites/${inviteId}/resend`, { method: "POST" });
}

export async function revokeInvite(inviteId: string): Promise<void> {
  await api(`/api/workspace/invites/${inviteId}`, { method: "DELETE" });
}

export async function setMemberRole(
  userId: string,
  role: "owner" | "admin" | "member",
): Promise<void> {
  await api(`/api/workspace/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export async function removeMember(userId: string): Promise<void> {
  await api(`/api/workspace/members/${userId}`, { method: "DELETE" });
}

export async function wipeOrg(domain: string): Promise<void> {
  await api("/api/org/wipe", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export async function listApiKeys(): Promise<ApiKey[]> {
  return api("/api/api-keys");
}

export async function createApiKey(label: string): Promise<{ id: string; key: string }> {
  return api("/api/api-keys", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export async function revokeApiKey(id: string): Promise<void> {
  await api(`/api/api-keys/${id}`, { method: "DELETE" });
}

export async function getMcpOAuthPending(
  rid: string,
): Promise<{ rid: string; client_name: string }> {
  return api(`/api/mcp/oauth/pending?rid=${encodeURIComponent(rid)}`);
}

export async function submitMcpOAuthConsent(
  rid: string,
  allow: boolean,
): Promise<{ redirect: string }> {
  return api("/api/mcp/oauth/consent", {
    method: "POST",
    body: JSON.stringify({ rid, allow }),
  });
}

export async function listConnectors(): Promise<ConnectorCard[]> {
  return api("/api/connectors");
}

export async function disconnectConnector(id: string): Promise<void> {
  await api(`/api/connectors/${id}`, { method: "DELETE" });
}

export async function syncConnector(id: string): Promise<{ job_id: string }> {
  return api(`/api/connectors/${id}/sync`, { method: "POST" });
}

export async function cancelConnector(id: string): Promise<void> {
  await api(`/api/connectors/${id}/cancel`, { method: "POST" });
}

export async function patchConnector(
  id: string,
  body: {
    interval_min?: number;
    paused?: boolean;
    lookback_days?: number;
    channel_ids?: string[];
  },
): Promise<ConnectorCard> {
  return api(`/api/connectors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function listSlackChannels(
  connectionId: string,
): Promise<Array<{ id: string; name: string; is_private: boolean }>> {
  const data = await api<{
    channels: Array<{ id: string; name: string; is_private: boolean }>;
  }>(`/api/connectors/${connectionId}/channels`);
  return data.channels;
}

export async function listJobs(connectionId: string): Promise<JobRow[]> {
  return api(`/api/connectors/${connectionId}/jobs`);
}

export async function getComposio(): Promise<ComposioStatus> {
  return api("/api/composio");
}

export async function setComposioKey(
  apiKey: string | null,
): Promise<Pick<ComposioStatus, "configured" | "key_source" | "masked_key">> {
  return api("/api/composio/key", {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function connectComposioToolkit(input: {
  toolkit: string;
  returnTo: "integrations" | "onboarding" | "connectors";
  lookbackDays?: number;
  personal?: boolean;
}): Promise<{ redirect_url: string }> {
  return api("/api/composio/connect", {
    method: "POST",
    body: JSON.stringify({
      toolkit: input.toolkit,
      return_to: input.returnTo,
      origin: window.location.origin,
      lookback_days: input.lookbackDays ?? 30,
      personal: input.personal ?? false,
    }),
  });
}

export async function listConversations(): Promise<Conversation[]> {
  return api("/api/conversations");
}

export async function createConversation(
  title?: string,
): Promise<Conversation> {
  return api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title: title ?? "New conversation" }),
  });
}

export async function getConversation(
  id: string,
): Promise<Conversation & { messages: Message[] }> {
  return api(`/api/conversations/${id}`);
}

export async function patchConversation(
  id: string,
  title: string,
): Promise<Conversation> {
  return api(`/api/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await api(`/api/conversations/${id}`, { method: "DELETE" });
}

export async function getSettings(): Promise<
  Settings & { raw?: Record<string, string> }
> {
  return api("/api/settings");
}

export async function putSettings(
  values: Record<string, string>,
): Promise<void> {
  await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ values }),
  });
}

export type WorkspaceResearchResult = {
  start_url: string;
  about: string;
  sources: { url: string; title: string; kind: string }[];
  pages_fetched: number;
  warnings: string[];
};

export async function researchWorkspaceWebsite(
  url: string,
): Promise<WorkspaceResearchResult> {
  return api("/api/workspace/research", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function disconnectSlack(): Promise<void> {
  await api("/api/slack/disconnect", { method: "POST" });
}

export async function testOutboundEmail(
  to?: string,
): Promise<{ status: string; provider: string }> {
  return api("/api/settings/email/test", {
    method: "POST",
    body: JSON.stringify({ to: to ?? "" }),
  });
}

export async function getProfile(): Promise<Profile | null> {
  return api("/api/profile");
}

export async function putProfile(display_name: string): Promise<void> {
  await api("/api/profile", {
    method: "PUT",
    body: JSON.stringify({ display_name }),
  });
}

export async function changePassword(
  current_password: string,
  new_password: string,
): Promise<void> {
  await api("/api/profile/password", {
    method: "PUT",
    body: JSON.stringify({ current_password, new_password }),
  });
}

export async function getHealth(): Promise<Health> {
  return api("/api/health");
}



/** Every layer: connectors → containers → documents → entities. */
export async function getGraphWorld(quality = true): Promise<GraphSlice> {
  const params = new URLSearchParams({ quality: String(quality) });
  return api(`/api/graph/world?${params}`);
}

export type AskHandlers = {
  onStatus?: (stage: string) => void;
  onRewritten?: (q: string, kind: string) => void;
  onPlan?: (lanes: string[], intent: string) => void;
  onLane?: (lane: string, hits: number) => void;
  onLive?: (checked: string[], found: boolean) => void;
  onToolCall?: (call: NonNullable<Message["tool_calls"]>[number]) => void;
  onToken?: (text: string) => void;
  /** Overwrite everything streamed so far with this authoritative text. */
  onReplace?: (text: string) => void;
  onCitations?: (citations: NonNullable<Message["citations"]>) => void;
  onReasoningPath?: (paths: string[]) => void;
  onDone?: (message: Message) => void;
};

/** SSE-over-POST via fetch ReadableStream (§12.2). */
export async function askStream(
  conversationId: string,
  question: string,
  handlers: AskHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}/api/ask`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, question }),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(apiMessage(text, `ask failed: ${res.status}`));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const chunk of parts) {
      const lines = chunk.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(data) as Record<string, unknown>;
      } catch {
        continue;
      }
      switch (event) {
        case "status":
          handlers.onStatus?.(String(payload.stage ?? ""));
          break;
        case "rewritten":
          handlers.onRewritten?.(
            String(payload.question ?? ""),
            String(payload.kind ?? "knowledge"),
          );
          break;
        case "plan":
          handlers.onPlan?.(
            (payload.lanes as string[]) ?? [],
            String(payload.intent ?? ""),
          );
          break;
        case "lane":
          handlers.onLane?.(
            String(payload.lane ?? ""),
            Number(payload.hits ?? 0),
          );
          break;
        case "tool_call":
          handlers.onToolCall?.(
            payload as unknown as NonNullable<Message["tool_calls"]>[number],
          );
          break;
        case "live":
          handlers.onLive?.(
            (payload.checked as string[]) ?? [],
            Boolean(payload.found),
          );
          break;
        case "token":
          handlers.onToken?.(String(payload.text ?? ""));
          break;
        case "replace":
          // The abstention gate disagreed with what was streamed (a
          // fabricated citation, a withdrawn answer). The streamed text is
          // display only; this is the authoritative text and must overwrite
          // it rather than append to it.
          handlers.onReplace?.(String(payload.text ?? ""));
          break;
        case "citations":
          handlers.onCitations?.(
            (payload.citations as NonNullable<Message["citations"]>) ?? [],
          );
          break;
        case "reasoning_path":
          handlers.onReasoningPath?.((payload.paths as string[]) ?? []);
          break;
        case "done":
          handlers.onDone?.(payload.message as Message);
          break;
        default:
          break;
      }
    }
  }
}
