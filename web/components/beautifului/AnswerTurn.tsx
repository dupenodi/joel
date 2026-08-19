"use client";

import { useState } from "react";
import { AbsentAnswer, NotFoundCallout } from "@/components/beautifului/NotFoundCallout";
import { AnswerBadge } from "@/components/beautifului/AnswerBadge";
import { CitationChip } from "@/components/beautifului/CitationChip";
import { ConflictBlock } from "@/components/beautifului/ConflictBlock";
import { LaneChips } from "@/components/beautifului/LaneChips";
import { ReasoningPath } from "@/components/beautifului/ReasoningPath";
import type { Message } from "@/lib/types";

export function UserTurn({ children }: { children: string }) {
  return (
    <div className="flex justify-end pl-10">
      <div className="rounded-[10px] bg-field px-3 py-2 text-[15px] leading-relaxed text-ink">
        {children}
      </div>
    </div>
  );
}

export function AnswerTurn({
  message,
  onForget,
}: {
  message: Message;
  onForget?: (docId: string) => void;
}) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const citations = (message.citations ?? []).filter(
    (c) => !hidden.has(c.doc_id),
  );

  function forget(docId: string) {
    setHidden((s) => new Set(s).add(docId));
    onForget?.(docId);
  }

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
            <CitationChip
              key={c.doc_id}
              citation={c}
              onForget={forget}
            />
          ))}
        </div>
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
