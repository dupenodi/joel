"use client";

import { ContentFrame } from "@/components/app-frame";
import { SimpleAnswer, UserTurn } from "@/components/beautifului/AnswerTurn";
import { MemoryBanner } from "@/components/beautifului/MemoryBanner";
import PromptBar from "@/components/beautifului/PromptBar";
import { ToolCallChips } from "@/components/beautifului/ToolCallChips";
import { BrandMark } from "@/components/brand-mark";
import { ThreadHistory } from "@/components/thread-history";
import { ChatBootSkeleton, ChatThreadSkeleton } from "@/components/skeletons";
import { Bone } from "@/components/beautifului/primitives/bone";
import { SourceIcon } from "@/components/source-icon";
import {
  askStream,
  createConversation,
  forgetDoc,
  getConversation,
  getOrg,
  getProfile,
  listConversations,
} from "@/lib/api";
import type { Conversation, Message, ToolCall } from "@/lib/types";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

/** Map backend stages → agent-action labels (same language as the sim). */
const STAGE_LABEL: Record<string, string> = {
  rewriting: "Planning",
  planning: "Planning",
  reranking: "Searching memory",
  live: "Checking live",
  answering: "Answering",
};

function welcomeCopy(name: string, org: string, memoryReady: boolean) {
  return {
    title: name ? `Hello, ${name}.` : "Hello.",
    line: memoryReady
      ? org
        ? `Ask about ${org}.`
        : "Ask a question."
      : org
        ? `Ask about ${org}. Nothing in memory yet — connect a tool when you're ready.`
        : "Ask a question. Nothing in memory yet.",
    ask: "Ask a question…",
  };
}

function ThinkingHeader({ label, working }: { label: string; working: boolean }) {
  return (
    <div className="-mx-1.5 flex w-fit items-center gap-2 rounded-control px-1.5 py-1">
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill={working ? "var(--ink-2)" : "var(--ink-3)"}
      >
        <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
      </svg>
      {working ? (
        <span
          className="bg-clip-text text-[13px] font-medium whitespace-nowrap text-transparent"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
            backgroundSize: "200% 100%",
            animation: "shimmer-text 1.4s linear infinite",
          }}
        >
          {label}
        </span>
      ) : (
        <span className="text-[13px] font-medium text-ink-2">{label}</span>
      )}
    </div>
  );
}

function RelHop({ path }: { path: string }) {
  const m = /^(.+?)\s*-\[:([^\]]+)\]->\s*(.+)$/.exec(path.trim());
  if (!m) {
    return (
      <p className="px-1.5 py-1 font-mono text-[11.5px] leading-relaxed text-ink-2">
        {path}
      </p>
    );
  }
  const [, from, edge, to] = m;
  const superseded = /superseded/i.test(path);
  return (
    <div
      className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-[6px] px-1.5 py-1 ${
        superseded ? "opacity-55" : ""
      }`}
    >
      <span className="rounded-full bg-inset px-2 py-0.5 text-[12px] font-medium text-ink shadow-hairline">
        {from.trim()}
      </span>
      <span className="font-mono text-[10.5px] tracking-[0.04em] text-ink-3">
        —[{edge}]→
      </span>
      <span className="rounded-full bg-inset px-2 py-0.5 text-[12px] font-medium text-ink shadow-hairline">
        {to.replace(/\s*\(.*$/, "").trim()}
      </span>
    </div>
  );
}

export function ChatSurface() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedId = searchParams.get("c");

  const [ready, setReady] = useState<boolean | null>(null);
  const [hello, setHello] = useState({ name: "", org: "" });
  const [profileReady, setProfileReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [stage, setStage] = useState<string | null>(null);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [reasoningPaths, setReasoningPaths] = useState<string[]>([]);
  const [liveProviders, setLiveProviders] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadPending, setThreadPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const loadGen = useRef(0);

  const loadList = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
    return list;
  }, []);

  useEffect(() => {
    getOrg()
      .then(async ({ org, checklist }) => {
        if (!org) {
          setReady(false);
          return;
        }
        setHello((h) => ({ ...h, org: org.name }));
        setReady(checklist.ready);
        await loadList();
      })
      .catch(() => setReady(false));
    getProfile()
      .then((p) => {
        const name = p?.display_name?.trim();
        if (name && name !== "You") {
          setHello((h) => ({ ...h, name: name.split(/\s+/)[0] ?? name }));
        }
      })
      .catch(() => {})
      .finally(() => setProfileReady(true));
  }, [loadList]);

  useEffect(() => {
    if (!requestedId || ready === null) return;
    if (requestedId === activeId) return;
    void selectConversation(requestedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedId, ready]);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, draft, stage, toolCalls, reasoningPaths]);

  async function selectConversation(id: string) {
    const seq = ++loadGen.current;
    setActiveId(id);
    setError(null);
    setMessages([]);
    setThreadPending(true);
    try {
      const conv = await getConversation(id);
      if (loadGen.current !== seq) return;
      setMessages(conv.messages);
      if (requestedId !== id) router.replace(`/?c=${id}`);
    } catch (e) {
      if (loadGen.current !== seq) return;
      setError(e instanceof Error ? e.message : "Could not load chat");
    } finally {
      if (loadGen.current === seq) setThreadPending(false);
    }
  }

  function clearWorking() {
    setStage(null);
    setToolCalls([]);
    setReasoningPaths([]);
    setLiveProviders([]);
    setDraft("");
  }

  async function onNewChat() {
    abortRef.current?.abort();
    setBusy(false);
    clearWorking();
    setActiveId(null);
    setMessages([]);
    setThreadPending(false);
    if (requestedId) router.replace("/");
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    clearWorking();
  }

  async function onSend(question: string) {
    if (!question.trim() || busy) return;
    setError(null);
    let conversationId = activeId;
    if (!conversationId) {
      const conv = await createConversation(question.slice(0, 72));
      conversationId = conv.id;
      setActiveId(conv.id);
      await loadList();
    }
    const user: Message = { role: "user", content: question };
    setMessages((m) => [...m, user]);
    setBusy(true);
    clearWorking();
    setStage("rewriting");

    const ac = new AbortController();
    abortRef.current = ac;
    let tokens = "";
    try {
      await askStream(
        conversationId,
        question,
        {
          onStatus: (s) => setStage(s),
          onToolCall: (call) =>
            setToolCalls((prev) => {
              const i = prev.findIndex((c) => c.id === call.id);
              if (i >= 0) {
                const next = [...prev];
                next[i] = call;
                return next;
              }
              return [...prev, call];
            }),
          onLive: (checked) => setLiveProviders(checked),
          onReasoningPath: (paths) => setReasoningPaths(paths),
          onToken: (text) => {
            tokens += text;
            setDraft(tokens);
          },
          onDone: (message) => {
            setMessages((m) => [...m, message]);
            clearWorking();
            void loadList();
          },
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Ask failed");
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  const empty = messages.length === 0 && !busy && !threadPending;
  const copy = welcomeCopy(hello.name, hello.org, ready === true);
  const threadLoading =
    threadPending || (Boolean(requestedId) && requestedId !== activeId);
  const thinkingLabel = stage
    ? (STAGE_LABEL[stage] ?? stage)
    : "Planning";
  const streaming = draft.length > 0;

  if (ready === null) {
    return <ChatBootSkeleton />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {ready === false && (
        <MemoryBanner
          kind="ingesting"
          action={
            <a
              href="/integrations"
              className="shrink-0 font-medium underline-offset-2 hover:underline"
            >
              Connect a tool
            </a>
          }
        >
          Nothing in memory yet. You can still ask — answers will be honest about
          what&apos;s missing.
        </MemoryBanner>
      )}
      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-y-auto">
        {threadLoading ? (
          <ChatThreadSkeleton />
        ) : empty ? (
          <ContentFrame
            width="chat"
            className="flex h-full min-h-full flex-col justify-center overflow-visible py-10"
          >
            <Welcome
              title={copy.title}
              line={copy.line}
              namePending={!profileReady}
            />
          </ContentFrame>
        ) : (
          <ContentFrame width="chat" className="flex flex-col gap-5 py-8">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <UserTurn key={m.id ?? `u-${i}`}>{m.content}</UserTurn>
              ) : (
                <SimpleAnswer
                  key={m.id ?? `a-${i}`}
                  message={m}
                  onForget={(docId) => void forgetDoc(docId)}
                />
              ),
            )}
            {busy && (
              <div className="flex flex-col gap-2">
                <ThinkingHeader
                  label={streaming ? "Answering" : thinkingLabel}
                  working={!streaming || stage === "answering"}
                />
                {reasoningPaths.length > 0 && (
                  <div className="ml-[5px] space-y-0.5 border-l border-line pl-3.5">
                    {reasoningPaths.map((p) => (
                      <RelHop key={p} path={p} />
                    ))}
                  </div>
                )}
                {toolCalls.length > 0 && <ToolCallChips calls={toolCalls} />}
                {liveProviders.length > 0 && toolCalls.length === 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {liveProviders.map((p) => (
                      <span
                        key={p}
                        className="inline-flex h-6 items-center gap-1.5 rounded-full bg-inset pr-2 pl-1.5 text-[11.5px] text-ink-2 shadow-hairline"
                      >
                        <SourceIcon provider={p} size={12} />
                        {p}
                      </span>
                    ))}
                  </div>
                )}
                {draft && (
                  <p className="text-[15px] leading-relaxed text-ink whitespace-pre-wrap">
                    {draft}
                    <span className="ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 rounded-full bg-ink" />
                  </p>
                )}
              </div>
            )}
            {error && <p className="text-[13px] text-red">{error}</p>}
          </ContentFrame>
        )}
      </div>

      <div className="shrink-0 pb-5">
        <ContentFrame width="chat">
          <div className="flex items-end gap-2">
            <ThreadHistory
              conversations={conversations}
              activeId={activeId}
              onSelect={(id) => void selectConversation(id)}
              onNew={() => void onNewChat()}
            />
            <div className="min-w-0 flex-1">
              <PromptBar
                tall={empty}
                placeholder={copy.ask}
                busy={busy}
                onSend={(text) => void onSend(text)}
                onStop={stop}
              />
            </div>
          </div>
          {empty && error && (
            <p className="mt-2 text-[13px] text-red">{error}</p>
          )}
        </ContentFrame>
      </div>
    </div>
  );
}

function Welcome({
  title,
  line,
  namePending,
}: {
  title: string;
  line: string;
  namePending?: boolean;
}) {
  return (
    <div className="mb-6 flex flex-col items-center text-center">
      <BrandMark size={288} animated />
      {namePending ? (
        <h1 className="mt-7 flex items-baseline justify-center gap-2 font-display text-[32px] leading-tight font-semibold tracking-tight text-ink">
          Hello, <Bone className="h-7 w-24" />
        </h1>
      ) : (
        <h1 className="mt-7 font-display text-[32px] leading-tight font-semibold tracking-tight text-ink">
          {title}
        </h1>
      )}
      <p className="mt-2.5 max-w-sm text-[16px] leading-relaxed text-ink-2">
        {line}
      </p>
    </div>
  );
}
