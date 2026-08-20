"use client";

import { useState } from "react";
import { AbsentAnswer, NotFoundCallout } from "@/components/beautifului/NotFoundCallout";
import { AnswerBadge } from "@/components/beautifului/AnswerBadge";
import { CitationChip } from "@/components/beautifului/CitationChip";
import { ConflictBlock } from "@/components/beautifului/ConflictBlock";
import { LaneChips } from "@/components/beautifului/LaneChips";
import { ReasoningPath } from "@/components/beautifului/ReasoningPath";
import { ToolCallChips } from "@/components/beautifului/ToolCallChips";
import { SourceIcon } from "@/components/source-icon";
import type { Citation, Message } from "@/lib/types";

export function UserTurn({ children }: { children: string }) {
  return (
    <div className="flex justify-end pl-10">
      <div className="rounded-[10px] bg-field px-3 py-2 text-[15px] leading-relaxed text-ink">
        {children}
      </div>
    </div>
  );
}

/** Settled answer for live chat — body + sources. No honesty badges. */
export function SimpleAnswer({ message }: { message: Message }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const citations = message.citations ?? [];
  const absent =
    message.status === "absent" ||
    (!message.content && citations.length === 0);

  return (
    <div className="flex w-full flex-col gap-2">
      {absent ? (
        <AbsentAnswer>
          {message.content || "Not in the company's memory."}
        </AbsentAnswer>
      ) : (
        <p className="text-[15px] leading-relaxed text-ink whitespace-pre-wrap">
          {message.content}
        </p>
      )}

      {citations.length > 0 && (
        <>
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              aria-expanded={sourcesOpen}
              onClick={() => setSourcesOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-[6px] px-1 py-0.5 text-left transition-colors duration-150 hover:bg-hover"
            >
              <span className="flex -space-x-1">
                {citations.slice(0, 4).map((c) => (
                  <span
                    key={c.doc_id}
                    className="flex size-3.5 items-center justify-center overflow-hidden rounded-full bg-surface shadow-[0_0_0_1.5px_var(--canvas)]"
                  >
                    <SourceIcon
                      provider={c.provider ?? c.source_type}
                      size={14}
                      className="rounded-full"
                    />
                  </span>
                ))}
              </span>
              <span className="text-[12px] text-ink-2">
                {citations.length} {citations.length === 1 ? "source" : "sources"}
              </span>
            </button>
          </div>

          {sourcesOpen && (
            <div className="flex flex-col rounded-[10px] bg-inset p-1 shadow-hairline">
              {citations.map((c) => (
                <SourceRow key={c.doc_id} citation={c} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SourceRow({ citation }: { citation: Citation }) {
  const provider = citation.provider ?? citation.source_type ?? undefined;
  return (
    <div className="flex items-center gap-2 rounded-[6px] px-1.5 py-1 text-[12px] text-ink-2 hover:bg-hover hover:text-ink">
      <a
        href={citation.url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="flex min-w-0 flex-1 items-center gap-2"
      >
        <SourceIcon provider={provider} size={16} className="rounded-[4px]" />
        <span className="min-w-0 truncate animated-underline">{citation.title}</span>
        {citation.live && (
          <span className="shrink-0 rounded-[4px] bg-accent px-1 py-px text-[9px] font-semibold tracking-[0.04em] text-white uppercase">
            Live
          </span>
        )}
        {provider && (
          <span className="ml-auto shrink-0 font-mono text-[10.5px] text-ink-3">
            {provider}
          </span>
        )}
      </a>
    </div>
  );
}

/** Gallery / rich honesty stack. Live chat uses SimpleAnswer. */
export function AnswerTurn({ message }: { message: Message }) {
  const citations = message.citations ?? [];

  return (
    <div className="flex w-full flex-col gap-2.5">
      {message.status && <AnswerBadge status={message.status} />}
      {message.status === "absent" ? (
        <AbsentAnswer>{message.content}</AbsentAnswer>
      ) : (
        <p className="text-[15px] leading-relaxed text-ink whitespace-pre-wrap">
          {message.content}
        </p>
      )}
      {message.conflicts?.map((c, i) => (
        <ConflictBlock
          key={i}
          positions={c.positions}
          assessment={c.assessment}
        />
      ))}
      {message.not_found && message.not_found.length > 0 && (
        <NotFoundCallout items={message.not_found} />
      )}
      {citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {citations.map((c) => (
            <CitationChip key={c.doc_id} citation={c} />
          ))}
        </div>
      )}
      {message.tool_calls && message.tool_calls.length > 0 && (
        <ToolCallChips calls={message.tool_calls} />
      )}
      {message.reasoning_path && message.reasoning_path.length > 0 && (
        <ReasoningPath paths={message.reasoning_path} />
      )}
      {message.lanes && message.lanes.length > 0 && (
        <LaneChips lanes={message.lanes} />
      )}
    </div>
  );
}
