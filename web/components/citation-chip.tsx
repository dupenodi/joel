"use client";

import { SourceIcon } from "@/components/source-icon";
import { Chip } from "@/components/ui/chip";
import { forgetDoc } from "@/lib/api";
import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useState } from "react";

export function CitationChip({
  citation,
  className,
}: {
  citation: Citation;
  className?: string;
}) {
  const [forgotten, setForgotten] = useState(false);
  if (forgotten) return null;

  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <a
        href={citation.url ?? "#"}
        target="_blank"
        rel="noreferrer"
        className="no-underline"
      >
        <Chip className="hover:border-[var(--line-strong)] hover:text-ink">
          <SourceIcon
            provider={citation.provider ?? citation.source_type}
            size={12}
          />
          {citation.live && (
            <span className="rounded bg-accent px-1 py-px text-[9px] font-semibold uppercase text-white">
              Live
            </span>
          )}
          {citation.title}
        </Chip>
      </a>
      <button
        type="button"
        className="text-[11px] text-muted underline-offset-2 hover:text-ink hover:underline"
        onClick={async () => {
          try {
            await forgetDoc(citation.doc_id);
            setForgotten(true);
          } catch {
            /* empty corpus — still hide locally */
            setForgotten(true);
          }
        }}
      >
        forget
      </button>
    </span>
  );
}
