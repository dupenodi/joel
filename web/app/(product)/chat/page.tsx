"use client";

import { ConversationItem } from "@/components/conversation-item";
import { EmptyState } from "@/components/empty-state";
import { MessageList } from "@/components/message-bubble";
import { AgentTrace } from "@/components/tool-call";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import {
  askStream,
  createConversation,
  getConversation,
  getOrg,
  listConversations,
} from "@/lib/api";
import type { Conversation, Message, ToolCall } from "@/lib/types";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

export default function ChatPage() {
  const [locked, setLocked] = useState<boolean | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [rewritten, setRewritten] = useState<string | null>(null);
  const [lanes, setLanes] = useState<Array<{ lane: string; hits: number }>>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshList = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
    return list;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const { checklist } = await getOrg();
        setLocked(!checklist.ready);
        if (checklist.ready) {
          const list = await refreshList();
          if (list[0]) {
            setActiveId(list[0].id);
          }
        }
      } catch {
        setLocked(true);
      }
    })();
  }, [refreshList]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    getConversation(activeId)
      .then((c) => setMessages(c.messages))
      .catch((e) => setError(e instanceof Error ? e.message : "Load failed"));
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText, toolCalls, lanes]);

  async function onNew() {
    const c = await createConversation();
    await refreshList();
    setActiveId(c.id);
    setMessages([]);
  }

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    const q = draft.trim();
    if (!q || streaming) return;
    setError(null);

    let convId = activeId;
    if (!convId) {
      const c = await createConversation(q.slice(0, 72));
      convId = c.id;
      setActiveId(c.id);
      await refreshList();
    }

    setDraft("");
    setStreaming(true);
    setStage("rewriting");
    setRewritten(null);
    setLanes([]);
    setToolCalls([]);
    setStreamText("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: q, created_at: new Date().toISOString() },
    ]);

    try {
      await askStream(convId, q, {
        onStatus: (s) => setStage(s),
        onRewritten: (rq) => setRewritten(rq),
        onPlan: (ls) =>
          setLanes(ls.map((lane) => ({ lane, hits: 0 }))),
        onLane: (lane, hits) =>
          setLanes((prev) =>
            prev.map((l) => (l.lane === lane ? { lane, hits } : l)),
          ),
        onToolCall: (call) =>
          setToolCalls((prev) => {
            const i = prev.findIndex((t) => t.id === call.id);
            if (i >= 0) {
              const next = [...prev];
              next[i] = call;
              return next;
            }
            return [...prev, call];
          }),
        onToken: (t) => setStreamText((s) => s + t),
        onDone: async (msg) => {
          setMessages((prev) => [...prev, msg]);
          setStreamText("");
          setStage(null);
          setRewritten(null);
          setLanes([]);
          setToolCalls([]);
          await refreshList();
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ask failed");
      setStage(null);
    } finally {
      setStreaming(false);
    }
  }

  if (locked === null) {
    return (
      <div className="px-6 py-10 text-sm text-muted">Loading…</div>
    );
  }

  if (locked) {
    return (
      <EmptyState
        title="Chat needs memory first"
        description="Connect a tool and wait for the first connector to reach ready."
        action={
          <Link href="/onboarding">
            <Button type="button">Go to onboarding</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex h-[calc(100vh)] min-h-[560px]">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-[var(--line)] bg-bg md:flex">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
          <span className="text-sm font-medium">Conversations</span>
          <IconButton aria-label="New conversation" onClick={() => void onNew()}>
            <Plus size={16} />
          </IconButton>
        </div>
        <ul className="flex-1 space-y-0.5 overflow-auto p-2">
          {conversations.length === 0 && (
            <li className="px-3 py-2 text-xs text-muted">No conversations yet</li>
          )}
          {conversations.map((c) => (
            <li key={c.id}>
              <ConversationItem
                conversation={c}
                active={c.id === activeId}
                onClick={() => setActiveId(c.id)}
              />
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-6 overflow-auto px-6 py-8">
          {messages.length === 0 && !streaming && (
            <p className="text-sm text-muted">
              Ask anything about the company. With an empty corpus, joel will
              say it honestly.
            </p>
          )}
          <MessageList messages={messages} />
          {streaming && (
            <div className="max-w-2xl space-y-3">
              <AgentTrace
                stage={stage}
                rewritten={rewritten}
                lanes={lanes}
                toolCalls={toolCalls}
              />
              {streamText && (
                <p className="text-[15px] leading-relaxed text-ink">
                  {streamText}
                  <span className="animate-pulse">▍</span>
                </p>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="px-6 pb-2 text-sm text-accent">{error}</p>
        )}

        <form
          className="border-t border-[var(--line)] p-4"
          onSubmit={(e) => void onAsk(e)}
        >
          <div className="mx-auto flex max-w-2xl gap-2">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask the company's memory…"
              disabled={streaming}
              className="flex-1 rounded-[var(--radius-sm)] border border-[var(--line)] bg-inset px-3.5 py-2.5 text-[15px] text-ink outline-none placeholder:text-muted focus:border-[var(--line-strong)] focus:bg-surface"
            />
            <Button type="submit" disabled={streaming || !draft.trim()}>
              Ask
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
