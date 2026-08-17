/** Browser client for joel-api (§12.2). */

import type {
  ConnectorCard,
  Conversation,
  Health,
  JobRow,
  Message,
  Org,
  Profile,
  ReadinessChecklist,
  Settings,
} from "./types";

const API = process.env.NEXT_PUBLIC_API ?? "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
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

export async function createOrg(domain: string): Promise<Org> {
  return api("/api/org", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export async function wipeOrg(domain: string): Promise<void> {
  await api("/api/org/wipe", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export async function listConnectors(): Promise<ConnectorCard[]> {
  return api("/api/connectors");
}

export async function connectProvider(
  provider: string,
  mode: "composio" | "oauth" = "composio",
): Promise<ConnectorCard> {
  return api("/api/connectors", {
    method: "POST",
    body: JSON.stringify({ provider, mode }),
  });
}

export async function disconnectConnector(id: string): Promise<void> {
  await api(`/api/connectors/${id}`, { method: "DELETE" });
}

export async function syncConnector(id: string): Promise<{ job_id: string }> {
  return api(`/api/connectors/${id}/sync`, { method: "POST" });
}

export async function patchConnector(
  id: string,
  body: { interval_min?: number; paused?: boolean },
): Promise<ConnectorCard> {
  return api(`/api/connectors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function listJobs(connectionId: string): Promise<JobRow[]> {
  return api(`/api/connectors/${connectionId}/jobs`);
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

export async function getProfile(): Promise<Profile | null> {
  return api("/api/profile");
}

export async function putProfile(display_name: string): Promise<void> {
  await api("/api/profile", {
    method: "PUT",
    body: JSON.stringify({ display_name }),
  });
}

export async function getHealth(): Promise<Health> {
  return api("/api/health");
}

export async function forgetDoc(docId: string): Promise<void> {
  await api(`/api/docs/${docId}/forget`, { method: "POST" });
}

export type AskHandlers = {
  onStatus?: (stage: string) => void;
  onRewritten?: (q: string, kind: string) => void;
  onPlan?: (lanes: string[], intent: string) => void;
  onLane?: (lane: string, hits: number) => void;
  onToolCall?: (call: NonNullable<Message["tool_calls"]>[number]) => void;
  onToken?: (text: string) => void;
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, question }),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(text || `ask failed: ${res.status}`);
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
        case "token":
          handlers.onToken?.(String(payload.text ?? ""));
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
