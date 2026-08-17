"use client";

import { ChatComposer } from "@/components/chat-composer";
import { ConversationItem } from "@/components/conversation-item";
import { EmptyState } from "@/components/empty-state";
import {
  ASSISTANT_BUBBLE_CLASS,
  ASSISTANT_TEXT_CLASS,
  MessageList,
} from "@/components/message-bubble";
import { ReasoningPath } from "@/components/reasoning-path";
import { AgentTrace } from "@/components/tool-call";
import { Button } from "@/components/ui/button";
import { CitationChip } from "@/components/citation-chip";
import { MobileDrawer } from "@/components/ui/drawer";
import { IconButton } from "@/components/ui/icon-button";
import { Spinner } from "@/components/ui/spinner";
import {
  askStream,
  createConversation,
  getConversation,
  getOrg,
  listConversations,
} from "@/lib/api";
import type { Citation, Conversation, Message, ToolCall } from "@/lib/types";
import { Plus, PanelLeft, X } from "lucide-react";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

export default function ChatPage() {
  const [locked, setLocked] = useState<boolean | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [rewritten, setRewritten] = useState<string | null>(null);
  const [lanes, setLanes] = useState<Array<{ lane: string; hits: number }>>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [streamText, setStreamText] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [reasoningPath, setReasoningPath] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(
    null,
  );
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamTextRef = useRef("");
  const toolCallsRef = useRef<ToolCall[]>([]);
  const lanesRef = useRef<Array<{ lane: string; hits: number }>>([]);
  const citationsRef = useRef<Citation[]>([]);
  const reasoningPathRef = useRef<string[]>([]);

  const refreshList = useCallback(async () => {
    setListLoading(true);
    try {
      const list = await listConversations();
      setConversations(list);
      setListError(null);
      return list;
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load conversations");
      return [];
    } finally {
      setListLoading(false);
    }
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

  function resetStreamState() {
    setStage(null);
    setRewritten(null);
    setLanes([]);
    setToolCalls([]);
    setStreamText("");
    setCitations([]);
    setReasoningPath([]);
    streamTextRef.current = "";
    toolCallsRef.current = [];
    lanesRef.current = [];
    citationsRef.current = [];
    reasoningPathRef.current = [];
  }

  async function onNew() {
    const c = await createConversation();
    await refreshList();
    setActiveId(c.id);
    setMessages([]);
  }

  async function runAsk(convId: string, question: string) {
    setError(null);
    setLastFailedQuestion(null);
    setStreaming(true);
    setStage("rewriting");
    resetStreamState();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await askStream(
        convId,
        question,
        {
          onStatus: (s) => setStage(s),
          onRewritten: (rq) => setRewritten(rq),
          onPlan: (ls) => {
            const next = ls.map((lane) => ({ lane, hits: 0 }));
            lanesRef.current = next;
            setLanes(next);
          },
          onLane: (lane, hits) =>
            setLanes((prev) => {
              const next = prev.map((l) =>
                l.lane === lane ? { lane, hits } : l,
              );
              lanesRef.current = next;
              return next;
            }),
          onToolCall: (call) =>
            setToolCalls((prev) => {
              const i = prev.findIndex((t) => t.id === call.id);
              const next =
                i >= 0
                  ? prev.map((t, idx) => (idx === i ? call : t))
                  : [...prev, call];
              toolCallsRef.current = next;
              return next;
            }),
          onToken: (t) =>
            setStreamText((s) => {
              const next = s + t;
              streamTextRef.current = next;
              return next;
            }),
          onCitations: (cs) => {
            citationsRef.current = cs;
            setCitations(cs);
          },
          onReasoningPath: (paths) => {
            reasoningPathRef.current = paths;
            setReasoningPath(paths);
          },
          onDone: async (msg) => {
            setMessages((prev) => [...prev, msg]);
            await refreshList();
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: streamTextRef.current,
            tool_calls: toolCallsRef.current,
            citations: citationsRef.current,
            reasoning_path: reasoningPathRef.current,
            lanes: lanesRef.current.map((l) => l.lane),
          },
        ]);
      } else {
        setError(err instanceof Error ? err.message : "Ask failed");
        setLastFailedQuestion(question);
      }
    } finally {
      resetStreamState();
      setStreaming(false);
      abortControllerRef.current = null;
    }
  }

  async function onAsk(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = draft.trim();
    if (!q || streaming) return;

    let convId = activeId;
    if (!convId) {
      const c = await createConversation(q.slice(0, 72));
      convId = c.id;
      setActiveId(c.id);
      await refreshList();
    }

    setDraft("");
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: q,
        created_at: new Date().toISOString(),
      },
    ]);

    await runAsk(convId, q);
  }

  async function onRetry() {
    if (!activeId || !lastFailedQuestion) return;
    await runAsk(activeId, lastFailedQuestion);
  }

  function onStop() {
    abortControllerRef.current?.abort();
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

  const activeTitle =
    conversations.find((c) => c.id === activeId)?.title ?? "New conversation";

  function renderConversationList(onSelect?: () => void) {
    return (
      <ul className="flex-1 space-y-0.5 overflow-auto p-2">
        {listLoading && conversations.length === 0 && (
          <li className="flex justify-center py-6">
            <Spinner size={18} />
          </li>
        )}
        {!listLoading && listError && (
          <li className="space-y-2 px-3 py-2 text-xs text-muted">
            <p>{listError}</p>
            <button
              type="button"
              className="text-ink underline underline-offset-2 hover:no-underline"
              onClick={() => void refreshList()}
            >
              Retry
            </button>
          </li>
        )}
        {!listLoading && !listError && conversations.length === 0 && (
          <li className="px-3 py-2 text-xs text-muted">No conversations yet</li>
        )}
        {conversations.map((c) => (
          <li key={c.id}>
            <ConversationItem
              conversation={c}
              active={c.id === activeId}
              onClick={() => {
                setActiveId(c.id);
                onSelect?.();
              }}
            />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-[var(--line)] bg-bg md:flex">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
          <span className="text-sm font-medium">Conversations</span>
          <IconButton aria-label="New conversation" onClick={() => void onNew()}>
            <Plus size={16} />
          </IconButton>
        </div>
        {renderConversationList()}
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3 md:hidden">
          <IconButton
            aria-label="Open conversations"
            onClick={() => setSidebarOpen(true)}
          >
            <PanelLeft size={18} />
          </IconButton>
          <span className="truncate px-2 text-sm font-medium">
            {activeTitle}
          </span>
          <IconButton aria-label="New conversation" onClick={() => void onNew()}>
            <Plus size={16} />
          </IconButton>
        </div>

        <div className="min-h-0 flex-1 space-y-6 overflow-auto px-6 py-8">
          {messages.length === 0 && !streaming && (
            <p className="text-sm text-muted">
              Ask anything about the company. With an empty corpus, joel will
              say it honestly.
            </p>
          )}
          <MessageList messages={messages} />
          {streaming && (
            <div className={ASSISTANT_BUBBLE_CLASS}>
              <AgentTrace
                stage={stage}
                rewritten={rewritten}
                lanes={lanes}
                toolCalls={toolCalls}
              />
              {citations.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {citations.map((c) => (
                    <CitationChip key={c.doc_id} citation={c} />
                  ))}
                </div>
              )}
              {reasoningPath.length > 0 && (
                <ReasoningPath paths={reasoningPath} />
              )}
              {streamText && (
                <p className={ASSISTANT_TEXT_CLASS}>
                  {streamText}
                  <span className="animate-pulse">▍</span>
                </p>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="flex items-center justify-between gap-3 px-6 pb-2 text-sm text-accent">
            <span>{error}</span>
            {lastFailedQuestion && (
              <button
                type="button"
                onClick={() => void onRetry()}
                className="shrink-0 underline underline-offset-2 hover:no-underline"
              >
                Retry
              </button>
            )}
          </div>
        )}

        <ChatComposer
          value={draft}
          onChange={setDraft}
          onSubmit={(e) => void onAsk(e)}
          onStop={onStop}
          busy={streaming}
          disabled={streaming}
        />
      </div>

      <MobileDrawer
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        label="Conversations"
      >
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
          <span className="text-sm font-medium">Conversations</span>
          <div className="flex items-center gap-1">
            <IconButton
              aria-label="New conversation"
              onClick={() => {
                void onNew();
                setSidebarOpen(false);
              }}
            >
              <Plus size={16} />
            </IconButton>
            <IconButton
              aria-label="Close conversations"
              onClick={() => setSidebarOpen(false)}
            >
              <X size={18} />
            </IconButton>
          </div>
        </div>
        {renderConversationList(() => setSidebarOpen(false))}
      </MobileDrawer>
    </div>
  );
}
