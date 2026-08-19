"use client";

import { ContentFrame } from "@/components/app-frame";
import { AnswerTurn, UserTurn } from "@/components/beautifului/AnswerTurn";
import { LaneChips } from "@/components/beautifului/LaneChips";
import { LockedChat } from "@/components/beautifului/LockedChat";
import PromptBar from "@/components/beautifului/PromptBar";
import { BrandMark } from "@/components/brand-mark";
import { ThreadHistory } from "@/components/thread-history";
import { ChatBootSkeleton, ChatThreadSkeleton } from "@/components/skeletons";
import { Bone } from "@/components/beautifului/primitives/bone";
import {
  askStream,
  createConversation,
  forgetDoc,
  getConversation,
  getOrg,
  getProfile,
  listConversations,
} from "@/lib/api";
import type { Conversation, Message } from "@/lib/types";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

const STAGE_LABEL: Record<string, string> = {
  rewriting: "Rewriting",
  planning: "Planning",
  reranking: "Reranking",
  live: "Checking live sources",
  answering: "Answering",
};

function welcomeCopy(name: string, org: string) {
  return {
    title: name ? `Hello, ${name}.` : "Hello.",
    line: org ? `Ask about ${org}.` : "Ask a question.",
    ask: "Ask a question",
  };
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
  const [liveLanes, setLiveLanes] = useState<string[]>([]);
  const [liveCheck, setLiveCheck] = useState<{ checked: string[]; found: boolean } | null>(
    null,
  );
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
          router.replace("/onboarding");
          return;
        }
        setHello((h) => ({ ...h, org: org.name }));
        setReady(checklist.ready);
        if (!checklist.ready) return;
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
  }, [loadList, router]);

  useEffect(() => {
    if (!requestedId || ready !== true) return;
    if (requestedId === activeId) return;
    void selectConversation(requestedId);
    // selectConversation is stable enough as a local function; we only react to id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedId, ready]);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, draft, stage]);

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

  async function onNewChat() {
    abortRef.current?.abort();
    setBusy(false);
    setDraft("");
    setStage(null);
    setLiveLanes([]);
    setLiveCheck(null);
    setActiveId(null);
    setMessages([]);
    setThreadPending(false);
    if (requestedId) router.replace("/");
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setStage(null);
    setLiveLanes([]);
    setLiveCheck(null);
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
    setDraft("");
    setStage("rewriting");
    setLiveLanes([]);
    setLiveCheck(null);

    const ac = new AbortController();
    abortRef.current = ac;
    let tokens = "";
    try {
      await askStream(
        conversationId,
        question,
        {
          onStatus: (s) => setStage(s),
          onLane: (lane) => setLiveLanes((ls) => (ls.includes(lane) ? ls : [...ls, lane])),
          onLive: (checked, found) => setLiveCheck({ checked, found }),
          onToken: (text) => {
            tokens += text;
            setDraft(tokens);
          },
          onDone: (message) => {
            setMessages((m) => [...m, message]);
            setDraft("");
            setStage(null);
            setLiveLanes([]);
            setLiveCheck(null);
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
  const copy = welcomeCopy(hello.name, hello.org);
  const threadLoading =
    threadPending || (Boolean(requestedId) && requestedId !== activeId);

  if (ready === null) {
    return <ChatBootSkeleton />;
  }

  if (!ready) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <LockedChat href="/integrations" />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
                <AnswerTurn
                  key={m.id ?? `a-${i}`}
                  message={m}
                  onForget={(docId) => void forgetDoc(docId)}
                />
              ),
            )}
            {busy && (
              <div className="flex flex-col gap-2">
                {stage && (
                  <span
                    className="w-fit bg-clip-text text-[14px] font-medium text-transparent"
                    style={{
                      backgroundImage:
                        "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
                      backgroundSize: "200% 100%",
                      animation: "shimmer-text 1.4s linear infinite",
                    }}
                  >
                    {STAGE_LABEL[stage] ?? stage}
                  </span>
                )}
                {liveLanes.length > 0 && <LaneChips lanes={liveLanes} />}
                {liveCheck && liveCheck.checked.length > 0 && (
                  <span className="text-[12.5px] text-ink-3">
                    Live: {liveCheck.checked.join(", ")}
                    {liveCheck.found ? " — found something new" : " — nothing new found"}
                  </span>
                )}
                {draft && (
                  <p className="text-[15px] leading-relaxed text-ink">
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
