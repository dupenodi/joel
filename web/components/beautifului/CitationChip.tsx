"use client";

import { SourceIcon } from "@/components/source-icon";
import type { Citation } from "@/lib/types";

export function CitationChip({
  citation,
  onForget,
}: {
  citation: Citation;
  onForget?: (docId: string) => void;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <a
        href={citation.url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="inline-flex h-6 max-w-56 items-center gap-1.5 rounded-full bg-inset pr-2 pl-1.5 text-[12px] font-medium text-ink-2 shadow-hairline transition-colors duration-150 hover:bg-hover hover:text-ink"
      >
        <SourceIcon
          provider={citation.provider ?? citation.source_type}
          size={12}
        />
        {citation.live && (
          <span className="rounded-[4px] bg-accent px-1 py-px text-[9px] font-semibold tracking-[0.04em] text-white uppercase">
            Live
          </span>
        )}
        <span className="truncate">{citation.title}</span>
      </a>
      {onForget && (
        <button
          type="button"
          onClick={() => onForget(citation.doc_id)}
          className="text-[11px] text-ink-3 underline-offset-2 transition-colors duration-150 hover:text-ink hover:underline"
        >
          forget
        </button>
      )}
    </span>
  );
}
